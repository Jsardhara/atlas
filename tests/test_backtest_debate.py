"""Tests for ``agents/architect/backtest_debate.py``.

Stubs the LLM debate + OHLC fetch so the harness logic (forward-return
scoring, summary aggregation, HTML rendering) is exercised without any
network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from architect import backtest_debate as bd  # type: ignore[import-not-found]


# ─────────────────────────────────────────────────────────────────────
# pure helpers
# ─────────────────────────────────────────────────────────────────────


def test_score_outcome_buy_correct():
    fwd, correct = bd._score_outcome("BUY", entry_price=100.0, forward_price=110.0)
    assert correct is True
    assert fwd == pytest.approx(0.10)


def test_score_outcome_buy_wrong():
    fwd, correct = bd._score_outcome("BUY", entry_price=100.0, forward_price=90.0)
    assert correct is False
    assert fwd == pytest.approx(-0.10)


def test_score_outcome_sell_correct():
    fwd, correct = bd._score_outcome("SELL", entry_price=100.0, forward_price=90.0)
    assert correct is True
    # Short P&L is positive when forward < entry; reported as +0.10.
    assert fwd == pytest.approx(0.10)


def test_score_outcome_hold_never_correct():
    fwd, correct = bd._score_outcome("HOLD", entry_price=100.0, forward_price=200.0)
    assert correct is False
    assert fwd == pytest.approx(1.0)  # raw return reported, not P&L


def test_score_outcome_zero_entry_safe():
    fwd, correct = bd._score_outcome("BUY", entry_price=0, forward_price=10)
    assert (fwd, correct) == (0.0, False)


def test_trade_dates_returns_lookback_count():
    out = bd._trade_dates(7)
    assert len(out) == 7
    today = datetime.now(timezone.utc).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    assert out[0] == yesterday  # newest first


def test_bar_index_at_or_after():
    bars = [[100, 1, 2, 0, 1.5, 1.4, 10, 1],
            [200, 1, 2, 0, 1.6, 1.5, 12, 2],
            [300, 1, 2, 0, 1.7, 1.6, 14, 3]]
    assert bd._bar_index_at_or_after(bars, 50) == 0
    assert bd._bar_index_at_or_after(bars, 200) == 1
    assert bd._bar_index_at_or_after(bars, 250) == 2
    assert bd._bar_index_at_or_after(bars, 999) is None


# ─────────────────────────────────────────────────────────────────────
# summary aggregation
# ─────────────────────────────────────────────────────────────────────


def _outcome(ticker, decision, entry, fwd, conviction=0.6):
    fwd_ret, correct = bd._score_outcome(decision, entry, fwd)
    return bd.TradeOutcome(
        ticker=ticker,
        trade_date="2026-05-01",
        decision=decision,
        winner="bull" if decision == "BUY" else "bear",
        conviction=conviction,
        entry_price=entry,
        forward_price=fwd,
        forward_return_pct=fwd_ret,
        correct=correct,
    )


def test_summary_zero_outcomes():
    s = bd._summarise([])
    assert s.total_signals == 0
    assert s.hit_rate == 0.0
    assert s.by_ticker == {}


def test_summary_perfect_hits():
    outcomes = [
        _outcome("AAPL", "BUY", 100, 105),
        _outcome("AAPL", "BUY", 100, 110),
        _outcome("MSFT", "SELL", 200, 180),
    ]
    s = bd._summarise(outcomes)
    assert s.total_signals == 3
    assert s.buy_signals == 2
    assert s.sell_signals == 1
    assert s.hit_rate == pytest.approx(1.0)
    assert s.by_ticker["AAPL"]["hit_rate"] == 1.0
    assert s.by_ticker["MSFT"]["hit_rate"] == 1.0


def test_summary_mixed_hits():
    outcomes = [
        _outcome("X", "BUY", 100, 110),  # correct
        _outcome("X", "BUY", 100, 95),   # wrong
        _outcome("X", "SELL", 200, 220), # wrong (price went up)
        _outcome("X", "SELL", 200, 180), # correct
    ]
    s = bd._summarise(outcomes)
    assert s.hit_rate == 0.5
    assert s.correct_buys == 1
    assert s.correct_sells == 1


def test_summary_holds_never_count_against_hit_rate():
    outcomes = [
        _outcome("X", "HOLD", 100, 110),
        _outcome("X", "HOLD", 100, 90),
        _outcome("X", "BUY", 100, 110),
    ]
    s = bd._summarise(outcomes)
    # Only the BUY is actionable; it was correct → 100%.
    assert s.hit_rate == 1.0
    assert s.hold_signals == 2


# ─────────────────────────────────────────────────────────────────────
# end-to-end harness with stubbed fetches
# ─────────────────────────────────────────────────────────────────────


def _make_bars(prices: list[float], start_date: str = "2026-04-01") -> list[list[float]]:
    """Synthetic daily bars: one per day starting at ``start_date``."""
    start = int(
        datetime.fromisoformat(f"{start_date}T00:00:00+00:00").timestamp()
    )
    out: list[list[float]] = []
    for i, p in enumerate(prices):
        ts = start + i * 86400
        out.append([ts, p, p * 1.02, p * 0.98, p, p, 1_000_000.0, 1])
    return out


@pytest.mark.asyncio
async def test_run_debate_backtest_writes_outputs(tmp_path, monkeypatch):
    # Synthetic OHLC: AAPL goes monotonically up; MSFT monotonically down.
    # Anchor 60 days back from today so the lookback window lands inside the bars.
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=60)).isoformat()
    bars_by_ticker = {
        "AAPL": _make_bars([100 + i for i in range(60)], start_date),
        "MSFT": _make_bars([200 - i for i in range(60)], start_date),
    }

    async def fake_fetch_ohlc(ticker, interval=1440, since=None):
        return bars_by_ticker.get(ticker, [])

    # Debate always says BUY for AAPL (correct → up) and SELL for MSFT (correct → down).
    async def fake_fetch_debate(symbol, *, trade_date, settings=None, redis=None,
                                 budget=None, market_context=None):
        decision = "BUY" if symbol == "AAPL" else "SELL"
        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "decision": decision,
            "rationale": "stubbed",
            "conviction": 0.7,
            "debate_log": {
                "bull": "x", "bear": "y",
                "winner": "bull" if decision == "BUY" else "bear",
            },
            "analyst_reports": {
                "fundamentals": "", "sentiment": "", "news": "", "technical": "",
            },
            "cost_usd": 0.0,
            "cached": False,
        }

    summary_dict = await bd.run_debate_backtest(
        tickers=("AAPL", "MSFT"),
        lookback_days=5,
        forward_bars=3,
        settings=object(),
        redis=None,
        fetch_ohlc_fn=fake_fetch_ohlc,
        fetch_debate_fn=fake_fetch_debate,
        out_dir=tmp_path,
    )

    # Most-recent trade dates lack forward_bars headroom; only the older
    # lookback dates produce outcomes (2 tickers × ~2 valid dates = 4).
    total = summary_dict["summary"]["total_signals"]
    assert total > 0
    assert total <= 10  # 2 tickers × 5 days upper bound
    assert summary_dict["summary"]["hit_rate"] == pytest.approx(1.0)

    json_files = list(Path(tmp_path).glob("debate_*.json"))
    html_files = list(Path(tmp_path).glob("debate_*.html"))
    assert len(json_files) == 1
    assert len(html_files) == 1
    payload = json.loads(json_files[0].read_text())
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert "AAPL" in payload["summary"]["by_ticker"]
    html = html_files[0].read_text()
    assert "Debate backtest" in html
    assert "AAPL" in html


@pytest.mark.asyncio
async def test_run_backtest_handles_no_bars(tmp_path):
    async def empty_ohlc(ticker, interval=1440, since=None):
        return []

    async def never_called(*args, **kwargs):
        raise AssertionError("debate must NOT run when bars are empty")

    summary = await bd.run_debate_backtest(
        tickers=("ZZZ",),
        lookback_days=3,
        forward_bars=2,
        settings=object(),
        redis=None,
        fetch_ohlc_fn=empty_ohlc,
        fetch_debate_fn=never_called,
        out_dir=tmp_path,
    )
    assert summary["summary"]["total_signals"] == 0


@pytest.mark.asyncio
async def test_run_backtest_drops_failed_debates(tmp_path):
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=60)).isoformat()
    bars = _make_bars([100 + i for i in range(60)], start_date)

    async def fake_ohlc(ticker, interval=1440, since=None):
        return bars

    call_count = {"n": 0}

    async def flaky_debate(symbol, *, trade_date, settings=None, redis=None,
                            budget=None, market_context=None):
        call_count["n"] += 1
        # Fail every other call.
        if call_count["n"] % 2 == 0:
            return None
        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "decision": "BUY",
            "conviction": 0.5,
            "debate_log": {"bull": "x", "bear": "y", "winner": "bull"},
            "analyst_reports": {},
            "cost_usd": 0,
            "cached": False,
            "rationale": "",
        }

    summary = await bd.run_debate_backtest(
        tickers=("AAPL",),
        lookback_days=4,
        forward_bars=2,
        settings=object(),
        redis=None,
        fetch_ohlc_fn=fake_ohlc,
        fetch_debate_fn=flaky_debate,
        out_dir=tmp_path,
    )
    # Some most-recent dates lack forward_bars headroom; flaky_debate
    # additionally drops every other call. Just assert *some* outcomes
    # landed and at least one was dropped.
    total_calls = call_count["n"]
    survived = summary["summary"]["total_signals"]
    assert total_calls > 0
    assert survived < total_calls
