"""Trader Kraken execution layer — places and monitors orders."""
import logging
import uuid

from sqlalchemy import text

from shared.config import Settings
from shared.db import get_session
from shared.kraken_client import KrakenClient

logger = logging.getLogger(__name__)


SHORT_MIN_LEVERAGE = 2
LONG_CASH_LEVERAGE = 1


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_win <= 0 or avg_loss <= 0:
        return 0.02
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    return max(0.005, min(kelly, 0.05))  # cap at 5% of portfolio


def _resolve_side_and_leverage(
    direction: str,
    requested_leverage: int,
    max_leverage: int,
) -> tuple[str, int]:
    """Map (direction, requested) -> (Kraken side, effective leverage).

    LONG cash: side=buy, leverage=1
    LONG margin: side=buy, leverage=requested
    SHORT: side=sell, leverage=max(2, requested), capped at max_leverage
    """
    direction = (direction or "").upper()
    if direction == "SHORT":
        leverage = max(SHORT_MIN_LEVERAGE, requested_leverage)
        leverage = min(leverage, max_leverage)
        return "sell", leverage
    if direction == "LONG":
        if requested_leverage <= 1:
            return "buy", LONG_CASH_LEVERAGE
        return "buy", min(requested_leverage, max_leverage)
    raise ValueError(f"Unsupported direction: {direction!r}")


class KrakenExecutor:
    def __init__(self, kraken: KrakenClient, settings: Settings):
        self.kraken = kraken
        self.settings = settings

    async def size_position(self, signal: dict) -> dict:
        """Calculate position size using Kelly criterion + risk limits.

        Symmetric for LONG and SHORT — direction does not change Kelly math.
        """
        async with get_session() as sess:
            # Get portfolio size
            snap = await sess.execute(text(
                "SELECT total_usd FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
            ))
            row = snap.fetchone()
            portfolio_usd = float(row[0]) if row else 1000.0

            # Get recent win stats
            stats = await sess.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE pnl_usd > 0)::float / NULLIF(COUNT(*), 0) as win_rate,
                    ABS(AVG(pnl_pct) FILTER (WHERE pnl_usd > 0)) as avg_win,
                    ABS(AVG(pnl_pct) FILTER (WHERE pnl_usd < 0)) as avg_loss
                FROM trades WHERE status = 'closed' AND closed_at >= now() - interval '30 days'
            """))
            s = stats.fetchone()
            wr = float(s[0] or 0.5)
            aw = float(s[1] or 0.02)
            al = float(s[2] or 0.02)

        fraction = kelly_fraction(wr, aw, al)
        size_usd = portfolio_usd * fraction

        # Confidence-based leverage suggestion (capped at MAX_LEVERAGE).
        confidence = signal.get("confidence", 0.6)
        direction = (signal.get("direction") or "").upper()
        if confidence >= 0.8:
            requested = min(3, self.settings.max_leverage)
        elif confidence >= 0.7:
            requested = min(2, self.settings.max_leverage)
        else:
            requested = 1

        # SHORT requires margin — bump to min if needed.
        if direction == "SHORT":
            requested = max(requested, SHORT_MIN_LEVERAGE)
        # Honor explicit signal.leverage if higher.
        if "leverage" in signal:
            try:
                requested = max(requested, int(signal["leverage"]))
            except (TypeError, ValueError):
                pass
        requested = min(requested, self.settings.max_leverage)

        return {
            "size_usd": round(size_usd, 2),
            "leverage": requested,
            "portfolio_usd": portfolio_usd,
            "kelly_fraction": round(fraction, 4),
        }

    async def execute_trade(
        self,
        signal: dict,
        sizing: dict,
        shortable_set: set[str] | None = None,
    ) -> dict:
        pair = signal["pair"]
        direction = (signal.get("direction") or "").upper()

        # Defensive SHORT eligibility — Guardian should have rejected non-shortable.
        if direction == "SHORT" and shortable_set is not None:
            altname = pair.replace("/", "")
            if altname not in shortable_set and pair not in shortable_set:
                return {
                    "error": f"SHORT rejected: {pair} not in shortable set",
                    "rejected": True,
                }

        side, effective_leverage = _resolve_side_and_leverage(
            direction,
            sizing.get("leverage", 1),
            self.settings.max_leverage,
        )
        sizing = {**sizing, "leverage": effective_leverage}

        # Convert USD size to base currency volume
        ticker = await self.kraken.get_ticker(pair.replace("/", ""))
        current_price = float(ticker.get("c", [signal.get("entry_price", 1)])[0]) if ticker else signal.get("entry_price", 1)
        volume = sizing["size_usd"] / current_price if current_price else 0.001

        order_result = await self.kraken.place_order(
            pair=pair.replace("/", ""),
            side=side,
            order_type="limit" if signal.get("entry_price") else "market",
            volume=round(volume, 6),
            price=signal.get("entry_price"),
            leverage=sizing["leverage"],
            validate=not self.settings.live_trading_enabled,
        )

        # Persist trade to DB
        trade_id = str(uuid.uuid4())
        is_paper = not self.settings.live_trading_enabled
        kraken_id = order_result.get("txid", [trade_id])[0] if isinstance(
            order_result.get("txid"), list) else order_result.get("txid", trade_id)

        async with get_session() as sess:
            await sess.execute(text("""
                INSERT INTO trades (id, signal_id, kraken_order_id, pair, side, order_type,
                                    leverage, requested_size, filled_size, entry_price,
                                    stop_loss, take_profit, status, is_paper,
                                    guardian_approved, opened_at)
                VALUES (:id, :signal_id::uuid, :kraken_id, :pair, :side, :order_type,
                        :leverage, :size, :filled, :entry, :sl, :tp,
                        'open', :paper, true, now())
            """), {
                "id": trade_id,
                "signal_id": signal.get("signal_id"),
                "kraken_id": kraken_id,
                "pair": pair,
                "side": side,
                "order_type": "limit" if signal.get("entry_price") else "market",
                "leverage": sizing["leverage"],
                "size": sizing["size_usd"],
                "filled": round(volume, 6),
                "entry": signal.get("entry_price") or current_price,
                "sl": signal.get("stop_loss"),
                "tp": signal.get("take_profit"),
                "paper": is_paper,
            })
            await sess.commit()

        logger.info("[Trader] Trade %s placed: %s %s %s vol=%.6f leverage=%dx paper=%s",
                    trade_id, side, pair, "PAPER" if is_paper else "LIVE",
                    volume, sizing["leverage"], is_paper)

        return {"trade_id": trade_id, "kraken_order_id": kraken_id,
                "pair": pair, "side": side, "size_usd": sizing["size_usd"],
                "leverage": sizing["leverage"], "is_paper": is_paper,
                "order_result": order_result}

    async def close_trade(self, trade_id: str) -> dict:
        async with get_session() as sess:
            row = await sess.execute(text(
                "SELECT pair, side, filled_size, requested_size, entry_price FROM trades WHERE id = :id"
            ), {"id": trade_id})
            trade = row.fetchone()
            if not trade:
                return {"error": "Trade not found"}

        entry = float(trade.entry_price or 1)
        # filled_size is base-currency volume; fall back to deriving it from USD size
        if trade.filled_size:
            volume = float(trade.filled_size)
        elif trade.requested_size and entry:
            volume = float(trade.requested_size) / entry
        else:
            volume = 0.001

        close_side = "sell" if trade.side == "buy" else "buy"
        await self.kraken.place_order(
            pair=trade.pair.replace("/", ""),
            side=close_side,
            order_type="market",
            volume=round(volume, 6),
            validate=not self.settings.live_trading_enabled,
        )

        # Update trade in DB
        async with get_session() as sess:
            ticker = await self.kraken.get_ticker(trade.pair.replace("/", ""))
            exit_price = float(ticker.get("c", [entry])[0]) if ticker else entry
            pnl_pct = (exit_price - entry) / entry if trade.side == "buy" else (entry - exit_price) / entry
            pnl_usd = pnl_pct * volume * entry

            await sess.execute(text("""
                UPDATE trades
                SET status = 'closed', exit_price = :exit, pnl_usd = :pnl_usd,
                    pnl_pct = :pnl_pct, closed_at = now(), close_reason = 'manual'
                WHERE id = :id
            """), {"exit": exit_price, "pnl_usd": round(pnl_usd, 4),
                   "pnl_pct": round(pnl_pct, 6), "id": trade_id})
            await sess.commit()

        return {"trade_id": trade_id, "status": "closed", "exit_price": exit_price}
