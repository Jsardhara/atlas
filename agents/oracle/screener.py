"""Stage-1 universe screener — cheap, no LLM.

Scores each USD pair on volume thrust, momentum, Bollinger position, and ATR
normalized by price. Returns top-N candidates ranked by absolute composite score.
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Literal

from .data_sources.kraken_market import PairInfo, fetch_ohlc

logger = logging.getLogger(__name__)

Direction = Literal["LONG", "SHORT", "NEUTRAL"]

# Score weights
W_VOLUME = 0.25
W_MOMENTUM = 0.35
W_BB = 0.25
W_ATR = 0.15

# Direction thresholds — composite score in [-1, 1] roughly after normalization.
LONG_THRESHOLD = 0.18
SHORT_THRESHOLD = -0.18

DEFAULT_TOP_N = 10
DEFAULT_MIN_VOLUME_USD_24H = 500_000.0
DEFAULT_INTERVAL_MIN = 5
DEFAULT_BARS_NEEDED = 60  # last 5h at 5m interval

# Bar columns from Kraken OHLC: [time, open, high, low, close, vwap, volume, count]
COL_TIME = 0
COL_OPEN = 1
COL_HIGH = 2
COL_LOW = 3
COL_CLOSE = 4
COL_VWAP = 5
COL_VOLUME = 6


@dataclass(frozen=True)
class Candidate:
    pair: str
    score: float
    suggested_direction: Direction
    shortable: bool
    snapshot: dict = field(default_factory=dict)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float], mean: float | None = None) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean if mean is not None else _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _atr(bars: list[list[float]], period: int = 14) -> float:
    """Average True Range over last `period` bars."""
    if len(bars) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(len(bars) - period, len(bars)):
        high = bars[i][COL_HIGH]
        low = bars[i][COL_LOW]
        prev_close = bars[i - 1][COL_CLOSE]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return _mean(trs)


def _bb_position(closes: list[float], period: int = 20) -> float:
    """Bollinger band position. (close - mid) / (2 * sigma) clamped to [-1, 1]."""
    if len(closes) < period:
        return 0.0
    window = closes[-period:]
    mid = _mean(window)
    sigma = _stdev(window, mid)
    if sigma == 0:
        return 0.0
    raw = (closes[-1] - mid) / (2 * sigma)
    return max(-1.0, min(1.0, raw))


def _volume_thrust(bars: list[list[float]], lookback: int = 12) -> float:
    """Current bar volume vs mean of prior `lookback` bars. Returns log-ratio clamped."""
    if len(bars) < lookback + 1:
        return 0.0
    recent_vol = bars[-1][COL_VOLUME]
    prior = [b[COL_VOLUME] for b in bars[-lookback - 1:-1]]
    avg = _mean(prior)
    if avg <= 0 or recent_vol <= 0:
        return 0.0
    ratio = recent_vol / avg
    log_ratio = math.log(ratio)
    # Map roughly to [-1, 1]: ratio of 2.7x -> ~1.0, 0.37x -> ~-1.0
    return max(-1.0, min(1.0, log_ratio))


def _momentum_pct(bars: list[list[float]], lookback_bars: int) -> float:
    if len(bars) < lookback_bars + 1:
        return 0.0
    past = bars[-lookback_bars - 1][COL_CLOSE]
    now = bars[-1][COL_CLOSE]
    if past <= 0:
        return 0.0
    pct = (now - past) / past
    # Clamp to ±10% mapped to ±1.0
    return max(-1.0, min(1.0, pct / 0.10))


def _atr_normalized(bars: list[list[float]], period: int = 14) -> float:
    """ATR / current close. Returns volatility magnitude in [0, 1] (mapped)."""
    if len(bars) < period + 1:
        return 0.0
    atr = _atr(bars, period)
    close = bars[-1][COL_CLOSE]
    if close <= 0:
        return 0.0
    raw = atr / close
    # Map ratio: 0.05 (5% ATR) -> 1.0
    return min(1.0, raw / 0.05)


def _last_24h_quote_volume(bars: list[list[float]], interval_min: int) -> float:
    """Approximate USD volume of last 24h from bars (volume * vwap)."""
    bars_per_day = max(1, int((24 * 60) / interval_min))
    window = bars[-bars_per_day:] if len(bars) >= bars_per_day else bars
    return sum(b[COL_VOLUME] * (b[COL_VWAP] or b[COL_CLOSE]) for b in window)


def score_pair(bars: list[list[float]], info: PairInfo) -> tuple[float, str]:
    """Composite signed score in roughly [-1, 1] and a short reasoning tag."""
    if len(bars) < 21:
        return 0.0, "insufficient_bars"

    vol_thrust = _volume_thrust(bars)
    momentum = _momentum_pct(bars, lookback_bars=12)  # ~1h on 5m bars
    bb_pos = _bb_position([b[COL_CLOSE] for b in bars])
    atr_norm = _atr_normalized(bars)

    # Directional score: vol thrust amplifies, but doesn't pick direction itself.
    # Momentum + bb overshoot drive direction. ATR is amplitude factor.
    directional = W_MOMENTUM * momentum + W_BB * bb_pos
    amplitude = W_VOLUME * abs(vol_thrust) + W_ATR * atr_norm

    # Composite: sign from directional, scaled by (1 + amplitude)
    if directional == 0:
        composite = 0.0
    else:
        sign = 1.0 if directional > 0 else -1.0
        composite = sign * min(1.0, abs(directional) + 0.5 * amplitude)

    tag = (
        f"mom={momentum:+.2f} bb={bb_pos:+.2f} "
        f"vol={vol_thrust:+.2f} atr={atr_norm:.2f}"
    )
    return composite, tag


def _direction_for(score: float, info: PairInfo) -> Direction:
    if score >= LONG_THRESHOLD:
        return "LONG"
    if score <= SHORT_THRESHOLD and info.shortable:
        return "SHORT"
    return "NEUTRAL"


def _build_snapshot(bars: list[list[float]], tag: str, vol_24h: float) -> dict:
    last = bars[-1]
    return {
        "close": last[COL_CLOSE],
        "high_24h": max(b[COL_HIGH] for b in bars[-288:]) if len(bars) >= 288 else max(b[COL_HIGH] for b in bars),
        "low_24h": min(b[COL_LOW] for b in bars[-288:]) if len(bars) >= 288 else min(b[COL_LOW] for b in bars),
        "volume_24h_quote": vol_24h,
        "bars_used": len(bars),
        "indicators": tag,
    }


async def _score_one(
    info: PairInfo,
    interval: int,
    min_volume_usd: float,
) -> Candidate | None:
    try:
        bars = await fetch_ohlc(info.altname, interval=interval)
    except Exception as exc:
        logger.warning("OHLC fetch failed for %s: %s", info.altname, exc)
        return None
    if len(bars) < 21:
        return None
    vol_24h = _last_24h_quote_volume(bars, interval)
    if vol_24h < min_volume_usd:
        return None

    score, tag = score_pair(bars, info)
    if score == 0.0:
        return None
    direction = _direction_for(score, info)
    snapshot = _build_snapshot(bars, tag, vol_24h)
    return Candidate(
        pair=info.wsname,
        score=score,
        suggested_direction=direction,
        shortable=info.shortable,
        snapshot=snapshot,
    )


async def screen_universe(
    pairs: list[PairInfo],
    top_n: int = DEFAULT_TOP_N,
    min_volume_usd_24h: float = DEFAULT_MIN_VOLUME_USD_24H,
    interval: int = DEFAULT_INTERVAL_MIN,
) -> list[Candidate]:
    """Score `pairs`, drop low-liquidity, return top `top_n` by abs(score)."""
    candidates: list[Candidate] = []
    # Sequential to respect 1 RPS limit (kraken_market enforces gap globally).
    for info in pairs:
        cand = await _score_one(info, interval, min_volume_usd_24h)
        if cand is not None:
            candidates.append(cand)

    candidates.sort(key=lambda c: abs(c.score), reverse=True)
    return candidates[:top_n]


async def screen_universe_parallel(
    pairs: list[PairInfo],
    top_n: int = DEFAULT_TOP_N,
    min_volume_usd_24h: float = DEFAULT_MIN_VOLUME_USD_24H,
    interval: int = DEFAULT_INTERVAL_MIN,
    concurrency: int = 1,
) -> list[Candidate]:
    """Concurrent variant — kraken_market still enforces global 1 RPS, so concurrency
    >1 only helps if rate-limit gets relaxed."""
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(info: PairInfo) -> Candidate | None:
        async with sem:
            return await _score_one(info, interval, min_volume_usd_24h)

    results = await asyncio.gather(*(_bounded(p) for p in pairs))
    candidates = [c for c in results if c is not None]
    candidates.sort(key=lambda c: abs(c.score), reverse=True)
    return candidates[:top_n]
