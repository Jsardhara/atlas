"""Verify Alpaca executor handles SHORT direction correctly.

Mirrors test_kraken_executor_short.py — same scenarios, alpaca executor.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from trader.alpaca_executor import (
    AlpacaExecutor,
    SHORT_MIN_LEVERAGE,
    _resolve_side_and_leverage,
)


# --- pure helper ---

def test_resolve_long_cash():
    side, lev = _resolve_side_and_leverage("LONG", 1, max_leverage=5)
    assert side == "buy"
    assert lev == 1


def test_resolve_long_margin_caps_at_max():
    side, lev = _resolve_side_and_leverage("LONG", 10, max_leverage=5)
    assert side == "buy"
    assert lev == 5


def test_resolve_short_forces_min_leverage():
    side, lev = _resolve_side_and_leverage("SHORT", 1, max_leverage=5)
    assert side == "sell"
    assert lev >= SHORT_MIN_LEVERAGE


def test_resolve_short_caps_at_max():
    side, lev = _resolve_side_and_leverage("SHORT", 10, max_leverage=3)
    assert side == "sell"
    assert lev == 3


def test_resolve_unknown_direction_raises():
    with pytest.raises(ValueError):
        _resolve_side_and_leverage("FOOBAR", 1, max_leverage=5)


def test_resolve_short_lowercase():
    side, lev = _resolve_side_and_leverage("short", 1, max_leverage=5)
    assert side == "sell"
    assert lev >= 2


# --- execute_trade SHORT flow ---

class _FakeAlpaca:
    def __init__(self):
        self.place_order = AsyncMock(return_value={"txid": ["ALPACA-FAKE-1"]})

    async def get_ticker(self, pair: str):
        return {"c": ["100.0"]}


@pytest.fixture
def fake_alpaca():
    return _FakeAlpaca()


@pytest.fixture
def settings():
    return SimpleNamespace(
        max_leverage=5,
        live_trading_enabled=False,
        alpaca_paper=True,
    )


@pytest.fixture
def patched_db(monkeypatch):
    """Stub get_session — alpaca_executor uses it for size_position + persist."""
    from trader import alpaca_executor as ae

    class _StubResult:
        def __init__(self, row=None):
            self._row = row
        def fetchone(self):
            return self._row
        def scalar(self):
            return self._row[0] if self._row else 0

    class _StubSession:
        async def execute(self, *a, **kw):
            sql = str(a[0]) if a else ""
            if "portfolio_snapshots" in sql:
                return _StubResult([10000.0])
            if "trades" in sql and "win_rate" in sql:
                return _StubResult([0.5, 0.02, 0.02])
            if "INSERT INTO trades" in sql:
                return _StubResult(None)
            return _StubResult(None)
        async def commit(self):
            pass

    class _CtxMgr:
        async def __aenter__(self):
            return _StubSession()
        async def __aexit__(self, *a):
            return None

    def _factory():
        return _CtxMgr()

    monkeypatch.setattr(ae, "get_session", _factory)


async def test_execute_short_uses_sell_side(fake_alpaca, settings, patched_db):
    executor = AlpacaExecutor(fake_alpaca, settings)
    signal = {
        "pair": "AAPL",
        "direction": "SHORT",
        "confidence": 0.75,
        "entry_price": 100.0,
        "signal_id": "00000000-0000-0000-0000-000000000001",
        "stop_loss": 105.0,
        "take_profit": 90.0,
    }
    sizing = {"size_usd": 200.0, "leverage": 1, "portfolio_usd": 10000.0, "kelly_fraction": 0.02}

    result = await executor.execute_trade(signal, sizing)

    fake_alpaca.place_order.assert_awaited_once()
    kwargs = fake_alpaca.place_order.await_args.kwargs
    assert kwargs["side"] == "sell"
    assert kwargs["leverage"] >= SHORT_MIN_LEVERAGE
    # validate=True forced when not live
    assert kwargs["validate"] is True
    assert result["side"] == "sell"
    assert result["leverage"] >= SHORT_MIN_LEVERAGE


async def test_execute_long_cash_uses_leverage_one(fake_alpaca, settings, patched_db):
    executor = AlpacaExecutor(fake_alpaca, settings)
    signal = {
        "pair": "AAPL",
        "direction": "LONG",
        "confidence": 0.65,
        "entry_price": 100.0,
        "signal_id": "00000000-0000-0000-0000-000000000002",
        "stop_loss": 95.0,
        "take_profit": 110.0,
    }
    sizing = {"size_usd": 200.0, "leverage": 1}

    await executor.execute_trade(signal, sizing)
    kwargs = fake_alpaca.place_order.await_args.kwargs
    assert kwargs["side"] == "buy"
    assert kwargs["leverage"] == 1


async def test_execute_short_rejected_when_not_shortable(fake_alpaca, settings, patched_db):
    executor = AlpacaExecutor(fake_alpaca, settings)
    signal = {
        "pair": "ADA/USD",
        "direction": "SHORT",
        "confidence": 0.7,
        "entry_price": 1.0,
        "signal_id": "00000000-0000-0000-0000-000000000003",
        "stop_loss": 1.05,
        "take_profit": 0.9,
    }
    sizing = {"size_usd": 100.0, "leverage": 2}

    result = await executor.execute_trade(signal, sizing, shortable_set={"AAPL"})
    assert result.get("rejected") is True
    fake_alpaca.place_order.assert_not_called()


async def test_size_position_short_min_leverage(monkeypatch, fake_alpaca, settings, patched_db):
    executor = AlpacaExecutor(fake_alpaca, settings)
    signal = {
        "pair": "AAPL",
        "direction": "SHORT",
        "confidence": 0.65,  # below the >=0.7 bracket
    }
    sizing = await executor.size_position(signal)
    assert sizing["leverage"] >= SHORT_MIN_LEVERAGE


async def test_size_position_long_high_confidence(monkeypatch, fake_alpaca, settings, patched_db):
    executor = AlpacaExecutor(fake_alpaca, settings)
    signal = {"pair": "AAPL", "direction": "LONG", "confidence": 0.85}
    sizing = await executor.size_position(signal)
    assert sizing["leverage"] >= 2
    assert sizing["leverage"] <= settings.max_leverage
