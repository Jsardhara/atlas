"""Hard rule validators — no LLM, pure logic.

Direction-aware (LONG/SHORT). All checks return ValidationResult.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from shared.db import get_session


@dataclass
class ValidationResult:
    passed: bool
    reason: str


MIN_CONFIDENCE = 0.6
MAX_OPEN_TRADES = 3


def _altname(pair: str) -> str:
    return pair.replace("/", "")


def _direction(signal: dict) -> str:
    return (signal.get("direction") or "").upper()


def _pair_info_from_asset_pairs(asset_pairs: dict, pair: str) -> dict | None:
    """Lookup an asset-pair record. Accepts wsname (BASE/QUOTE) or altname."""
    altname = _altname(pair)
    if altname in asset_pairs:
        return asset_pairs[altname]
    # Fallback: scan for wsname match
    for key, info in asset_pairs.items():
        if not isinstance(info, dict):
            continue
        if info.get("wsname") == pair or info.get("altname") == altname or key == pair:
            return info
    return None


def _max_leverage_for(pair_info: dict, side: str) -> int:
    """Highest leverage from the AssetPairs entry for given side ("buy"|"sell")."""
    key = "leverage_buy" if side == "buy" else "leverage_sell"
    raw = pair_info.get(key, []) if pair_info else []
    try:
        values = [int(x) for x in raw]
    except (TypeError, ValueError):
        return 0
    return max(values) if values else 0


def check_short_eligibility(signal: dict, asset_pairs: dict) -> ValidationResult:
    """Reject SHORT on a pair with no leverage_sell entries."""
    if _direction(signal) != "SHORT":
        return ValidationResult(True, "not a SHORT")
    pair = signal.get("pair", "")
    info = _pair_info_from_asset_pairs(asset_pairs or {}, pair)
    if info is None:
        return ValidationResult(False, f"SHORT rejected: pair {pair} not in AssetPairs")
    if _max_leverage_for(info, "sell") <= 0:
        return ValidationResult(False, f"SHORT rejected: {pair} not margin-eligible (leverage_sell empty)")
    return ValidationResult(True, "shortable")


def check_leverage_cap(
    signal: dict,
    settings: Any,
    pair_info: dict | None = None,
) -> ValidationResult:
    """Reject if leverage exceeds min(MAX_LEVERAGE, pair max for the side)."""
    requested = signal.get("leverage")
    if requested is None:
        return ValidationResult(True, "no leverage requested")
    try:
        requested = int(requested)
    except (TypeError, ValueError):
        return ValidationResult(False, f"leverage {requested!r} not an int")

    cap = int(getattr(settings, "max_leverage", 1))
    if pair_info is not None:
        side = "sell" if _direction(signal) == "SHORT" else "buy"
        pair_max = _max_leverage_for(pair_info, side)
        if pair_max > 0:
            cap = min(cap, pair_max)
        elif _direction(signal) == "SHORT":
            return ValidationResult(False, "leverage cap: pair not shortable")

    if requested > cap:
        return ValidationResult(False, f"leverage {requested} exceeds cap {cap}")
    if requested < 1:
        return ValidationResult(False, f"leverage {requested} below 1")
    return ValidationResult(True, f"leverage {requested} within cap {cap}")


def check_sl_tp_geometry(signal: dict) -> ValidationResult:
    """Direction-aware SL/TP placement.

    LONG: SL < entry < TP
    SHORT: TP < entry < SL
    """
    direction = _direction(signal)
    entry = signal.get("entry_price")
    sl = signal.get("stop_loss")
    tp = signal.get("take_profit")

    if entry is None or sl is None or tp is None:
        return ValidationResult(True, "geometry: missing entry/sl/tp — skipped")

    try:
        entry = float(entry)
        sl = float(sl)
        tp = float(tp)
    except (TypeError, ValueError):
        return ValidationResult(False, "geometry: non-numeric entry/sl/tp")

    if direction == "LONG":
        if not (sl < entry < tp):
            return ValidationResult(False, f"LONG geometry: need SL<{entry}<TP, got SL={sl} TP={tp}")
        return ValidationResult(True, "LONG geometry ok")
    if direction == "SHORT":
        if not (tp < entry < sl):
            return ValidationResult(False, f"SHORT geometry: need TP<{entry}<SL, got SL={sl} TP={tp}")
        return ValidationResult(True, "SHORT geometry ok")
    return ValidationResult(False, f"unknown direction {direction!r}")


async def validate_hard_rules(
    signal: dict,
    settings: Any,
    asset_pairs: dict | None = None,
) -> ValidationResult:
    """Run all hard rules. Each returns first failure."""
    pair = signal.get("pair", "")
    confidence = signal.get("confidence", 0)

    # Min confidence check
    if confidence < MIN_CONFIDENCE:
        return ValidationResult(False, f"Confidence {confidence:.2f} below minimum {MIN_CONFIDENCE:.2f}")

    # Direction sanity
    direction = _direction(signal)
    if direction not in {"LONG", "SHORT"}:
        return ValidationResult(False, f"Unsupported direction {direction!r}")

    # Pair info lookup once
    pair_info = _pair_info_from_asset_pairs(asset_pairs or {}, pair) if asset_pairs else None

    # SHORT eligibility
    if asset_pairs is not None:
        elig = check_short_eligibility(signal, asset_pairs)
        if not elig.passed:
            return elig

    # Leverage cap (pair-aware when info available)
    lev = check_leverage_cap(signal, settings, pair_info)
    if not lev.passed:
        return lev

    # SL/TP geometry
    geom = check_sl_tp_geometry(signal)
    if not geom.passed:
        return geom

    async with get_session() as sess:
        # Max open trades
        count_row = await sess.execute(text(
            "SELECT COUNT(*) FROM trades WHERE status = 'open'"
        ))
        open_count = count_row.scalar()
        if open_count >= MAX_OPEN_TRADES:
            return ValidationResult(False, f"Max open trades reached ({open_count}/{MAX_OPEN_TRADES})")

        # Duplicate pair (independent of direction — one position per pair)
        dup = await sess.execute(text(
            "SELECT id FROM trades WHERE pair = :pair AND status = 'open' LIMIT 1"
        ), {"pair": pair})
        if dup.fetchone():
            return ValidationResult(False, f"Already have open position in {pair}")

        # Daily loss circuit breaker — pnl_usd already signed; ABS sums losses correctly
        # for both LONG and SHORT (loss is negative pnl regardless of direction).
        loss_row = await sess.execute(text("""
            SELECT COALESCE(SUM(ABS(pnl_usd)), 0)
            FROM trades WHERE pnl_usd < 0 AND closed_at >= CURRENT_DATE
        """))
        daily_loss = float(loss_row.scalar())
        if daily_loss >= settings.daily_loss_limit_usd:
            return ValidationResult(False, f"Daily loss limit hit (${daily_loss:.2f})")

        # Portfolio risk check — uses |entry - sl| / entry, symmetric for LONG/SHORT.
        portfolio_row = await sess.execute(text(
            "SELECT total_usd FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
        ))
        portfolio_row = portfolio_row.fetchone()
        if portfolio_row:
            entry = signal.get("entry_price", 0)
            stop = signal.get("stop_loss", 0)
            if entry and stop:
                risk_pct = abs(entry - stop) / entry
                if risk_pct > settings.max_portfolio_risk_pct:
                    return ValidationResult(False,
                        f"Risk per trade {risk_pct:.1%} exceeds max {settings.max_portfolio_risk_pct:.1%}")

    return ValidationResult(True, "All hard rules passed")
