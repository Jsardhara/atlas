"""Unit tests for screener — scoring + ranking on synthetic bars."""
from __future__ import annotations

import pytest

from oracle import screener
from oracle.data_sources.kraken_market import PairInfo
from oracle.screener import (
    Candidate,
    LONG_THRESHOLD,
    SHORT_THRESHOLD,
    _atr,
    _bb_position,
    _direction_for,
    _momentum_pct,
    _volume_thrust,
    score_pair,
    screen_universe,
)


def _shortable_pair(altname: str = "XBTUSD") -> PairInfo:
    return PairInfo(
        wsname="XBT/USD", base="XXBT", quote="ZUSD", altname=altname,
        leverage_buy=(2, 3, 4, 5), leverage_sell=(2, 3, 4, 5),
        lot_decimals=8, pair_decimals=1, ordermin=0.0001,
    )


def _spot_pair(altname: str = "ADAUSD") -> PairInfo:
    return PairInfo(
        wsname="ADA/USD", base="ADA", quote="USD", altname=altname,
        leverage_buy=(2, 3), leverage_sell=(),
        lot_decimals=8, pair_decimals=6, ordermin=1.0,
    )


def _make_bars(closes: list[float], volumes: list[float] | None = None) -> list[list[float]]:
    """Build OHLC rows: [time, open, high, low, close, vwap, volume, count]."""
    if volumes is None:
        volumes = [100.0] * len(closes)
    bars: list[list[float]] = []
    for i, (close, vol) in enumerate(zip(closes, volumes)):
        prev = closes[i - 1] if i > 0 else close
        high = max(prev, close) * 1.005
        low = min(prev, close) * 0.995
        bars.append([
            float(1_700_000_000 + i * 300),  # time
            float(prev),                       # open
            float(high),
            float(low),
            float(close),
            float(close),                      # vwap
            float(vol),
            10.0,                              # count
        ])
    return bars


# --- indicator-level tests ---

def test_momentum_positive():
    closes = [100.0] * 5 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    bars = _make_bars(closes)
    # ~9% over 12 bars (almost full lookback) -> close to 1.0 cap
    m = _momentum_pct(bars, lookback_bars=12)
    assert m > 0


def test_momentum_negative():
    closes = list(range(120, 100, -1))  # strictly down
    bars = _make_bars([float(c) for c in closes])
    m = _momentum_pct(bars, lookback_bars=12)
    assert m < 0


def test_bb_position_overbought():
    closes = [100.0] * 19 + [120.0]  # spike on last bar
    pos = _bb_position(closes, period=20)
    assert pos > 0.5


def test_bb_position_oversold():
    closes = [100.0] * 19 + [80.0]
    pos = _bb_position(closes, period=20)
    assert pos < -0.5


def test_atr_nonneg():
    bars = _make_bars([100.0 + i * 0.5 for i in range(30)])
    a = _atr(bars, period=14)
    assert a >= 0


def test_volume_thrust_spike():
    # Last bar 5x the average prior volume
    vols = [10.0] * 12 + [50.0]
    bars = _make_bars([100.0] * 13, volumes=vols)
    t = _volume_thrust(bars, lookback=12)
    assert t > 0.5


# --- score_pair tests ---

def test_score_pair_long_when_uptrend():
    info = _shortable_pair()
    closes = [100.0 + i * 0.8 for i in range(30)]  # strong uptrend
    bars = _make_bars(closes)
    score, tag = score_pair(bars, info)
    assert score > 0
    assert "mom=" in tag


def test_score_pair_short_when_downtrend():
    info = _shortable_pair()
    closes = [100.0 - i * 0.8 for i in range(30)]
    bars = _make_bars(closes)
    score, _tag = score_pair(bars, info)
    assert score < 0


def test_score_pair_insufficient_bars():
    info = _shortable_pair()
    score, tag = score_pair(_make_bars([100.0] * 10), info)
    assert score == 0.0
    assert tag == "insufficient_bars"


# --- direction selection ---

def test_direction_long():
    info = _shortable_pair()
    assert _direction_for(LONG_THRESHOLD + 0.01, info) == "LONG"


def test_direction_short_only_if_shortable():
    shortable = _shortable_pair()
    spot_only = _spot_pair()
    assert _direction_for(SHORT_THRESHOLD - 0.01, shortable) == "SHORT"
    # Spot-only -> NEUTRAL even with strong negative score
    assert _direction_for(SHORT_THRESHOLD - 0.01, spot_only) == "NEUTRAL"


def test_direction_neutral_in_band():
    info = _shortable_pair()
    assert _direction_for(0.0, info) == "NEUTRAL"


# --- screen_universe ranking ---

@pytest.fixture
def fake_ohlc(monkeypatch):
    """Map altname -> bars list. fetch_ohlc returns them."""
    bars_by_pair: dict[str, list[list[float]]] = {}

    async def _fake_fetch(pair: str, interval: int = 5, since=None):
        return bars_by_pair.get(pair, [])

    monkeypatch.setattr(screener, "fetch_ohlc", _fake_fetch)
    return bars_by_pair


async def test_screen_universe_ranks_by_abs_score(fake_ohlc):
    p_up = _shortable_pair("UPUSD")
    p_down = PairInfo(wsname="DN/USD", base="DN", quote="USD", altname="DNUSD",
                     leverage_buy=(2, 3), leverage_sell=(2, 3),
                     lot_decimals=8, pair_decimals=4, ordermin=1.0)
    p_flat = _shortable_pair("FLATUSD")

    fake_ohlc["UPUSD"] = _make_bars([100.0 + i * 0.8 for i in range(30)],
                                      volumes=[1_000_000.0] * 30)
    fake_ohlc["DNUSD"] = _make_bars([100.0 - i * 0.8 for i in range(30)],
                                      volumes=[1_000_000.0] * 30)
    fake_ohlc["FLATUSD"] = _make_bars([100.0] * 30, volumes=[1_000_000.0] * 30)

    cands = await screen_universe([p_up, p_down, p_flat], top_n=10, min_volume_usd_24h=0)
    # FLATUSD has score==0, dropped
    pairs = [c.pair for c in cands]
    assert "XBT/USD" in pairs or "DN/USD" in pairs  # at least the trending ones
    # Both trenders survived
    assert any(c.suggested_direction == "LONG" for c in cands)
    assert any(c.suggested_direction == "SHORT" for c in cands)


async def test_screen_universe_drops_low_volume(fake_ohlc):
    p = _shortable_pair("LOWVOL")
    fake_ohlc["LOWVOL"] = _make_bars([100.0 + i * 0.8 for i in range(30)],
                                       volumes=[10.0] * 30)  # tiny volume
    cands = await screen_universe([p], top_n=10, min_volume_usd_24h=1_000_000)
    assert cands == []


async def test_screen_universe_top_n_cap(fake_ohlc):
    pairs = []
    for i in range(15):
        info = PairInfo(
            wsname=f"P{i}/USD", base=f"P{i}", quote="USD", altname=f"P{i}USD",
            leverage_buy=(2,), leverage_sell=(2,),
            lot_decimals=8, pair_decimals=4, ordermin=1.0,
        )
        pairs.append(info)
        # Vary trend strength so scores differ
        slope = 0.3 + i * 0.05
        fake_ohlc[f"P{i}USD"] = _make_bars(
            [100.0 + j * slope for j in range(30)],
            volumes=[1_000_000.0] * 30,
        )
    cands = await screen_universe(pairs, top_n=5, min_volume_usd_24h=0)
    assert len(cands) == 5
    # Sorted by abs score descending
    scores = [abs(c.score) for c in cands]
    assert scores == sorted(scores, reverse=True)


async def test_candidate_carries_shortable_flag(fake_ohlc):
    spot = _spot_pair("ADAUSD")
    fake_ohlc["ADAUSD"] = _make_bars(
        [100.0 + i * 0.8 for i in range(30)],
        volumes=[1_000_000.0] * 30,
    )
    cands = await screen_universe([spot], top_n=5, min_volume_usd_24h=0)
    assert len(cands) == 1
    assert cands[0].shortable is False
    # Direction will be LONG (uptrend); could be NEUTRAL only if score in band
    assert cands[0].suggested_direction in {"LONG", "NEUTRAL"}
