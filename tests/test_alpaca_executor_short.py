"""Verify Alpaca executor handles SHORT direction correctly."""
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


# --- fractional-short rounding ---

class _FakeAlpacaPriced:
    def __init__(self, price: float):
        self._price = price
        self.place_order = AsyncMock(return_value={"txid": ["ALPACA-FAKE-X"]})

    async def get_ticker(self, pair: str):
        return {"c": [str(self._price)]}


async def test_execute_short_rounds_fractional_to_one_share(settings, patched_db):
    """qty < 1 on SHORT must round up to 1 (Alpaca rejects fractional shorts).

    Sizing $300 / price $510 = 0.59 shares → fractional. 1-share notional
    $510 stays within 2x sizing cap ($600), so rounding to 1 is allowed.
    """
    fake = _FakeAlpacaPriced(price=510.0)
    executor = AlpacaExecutor(fake, settings)
    signal = {
        "pair": "TMO",
        "direction": "SHORT",
        "confidence": 0.7,
        "entry_price": 510.0,
        "signal_id": "00000000-0000-0000-0000-000000000010",
        "stop_loss": 530.0,
        "take_profit": 460.0,
    }
    sizing = {"size_usd": 300.0, "leverage": 2}

    result = await executor.execute_trade(signal, sizing)
    fake.place_order.assert_awaited_once()
    kwargs = fake.place_order.await_args.kwargs
    assert kwargs["side"] == "sell"
    assert kwargs["volume"] == 1.0  # rounded up
    assert result.get("rejected") is not True


async def test_execute_short_skips_when_one_share_exceeds_2x_sizing(settings, patched_db):
    """If 1-share notional > 2x Kelly size, skip cleanly."""
    # $30 sizing × 2x cap = $60 max. NVDA $900/share blows past it.
    fake = _FakeAlpacaPriced(price=900.0)
    executor = AlpacaExecutor(fake, settings)
    signal = {
        "pair": "NVDA",
        "direction": "SHORT",
        "confidence": 0.7,
        "entry_price": 900.0,
        "signal_id": "00000000-0000-0000-0000-000000000011",
        "stop_loss": 945.0,
        "take_profit": 810.0,
    }
    sizing = {"size_usd": 30.0, "leverage": 2}

    result = await executor.execute_trade(signal, sizing)
    fake.place_order.assert_not_called()
    assert result.get("rejected") is True
    assert "1-share cost" in result.get("error", "")


async def test_execute_short_rejects_crypto_pair(settings, patched_db):
    """Alpaca crypto is spot-only — SHORT must be rejected before submit."""
    fake = _FakeAlpacaPriced(price=70000.0)
    executor = AlpacaExecutor(fake, settings)
    signal = {
        "pair": "BTC/USD",
        "direction": "SHORT",
        "confidence": 0.7,
        "entry_price": 70000.0,
        "signal_id": "00000000-0000-0000-0000-000000000012",
        "stop_loss": 73500.0,
        "take_profit": 63000.0,
    }
    sizing = {"size_usd": 100.0, "leverage": 2}

    result = await executor.execute_trade(signal, sizing)
    fake.place_order.assert_not_called()
    assert result.get("rejected") is True
    assert "crypto" in result.get("error", "").lower()


async def test_execute_short_skips_when_not_easy_to_borrow(settings, patched_db):
    """Live ETB check — if Alpaca says easy_to_borrow=False, skip the SHORT."""

    class _FakeAlpacaETB:
        def __init__(self, price: float, etb: bool):
            self._price = price
            self._etb = etb
            self.place_order = AsyncMock(return_value={"txid": ["X"]})

        async def get_ticker(self, pair: str):
            return {"c": [str(self._price)]}

        async def get_asset(self, symbol: str):
            return {
                "symbol": symbol,
                "tradable": True,
                "shortable": True,
                "easy_to_borrow": self._etb,
                "marginable": True,
                "fractionable": True,
                "asset_class": "us_equity",
            }

    fake = _FakeAlpacaETB(price=120.0, etb=False)
    executor = AlpacaExecutor(fake, settings)
    signal = {
        "pair": "GME",
        "direction": "SHORT",
        "confidence": 0.75,
        "entry_price": 120.0,
        "signal_id": "00000000-0000-0000-0000-000000000020",
        "stop_loss": 130.0,
        "take_profit": 100.0,
    }
    sizing = {"size_usd": 200.0, "leverage": 2}

    result = await executor.execute_trade(signal, sizing)
    fake.place_order.assert_not_called()
    assert result.get("rejected") is True
    assert "easy-to-borrow" in result.get("error", "").lower()


async def test_execute_long_keeps_fractional(settings, patched_db):
    """Fractional rule does NOT apply to LONG — fractional buys are fine on Alpaca."""
    fake = _FakeAlpacaPriced(price=510.0)
    executor = AlpacaExecutor(fake, settings)
    signal = {
        "pair": "TMO",
        "direction": "LONG",
        "confidence": 0.7,
        "entry_price": 510.0,
        "signal_id": "00000000-0000-0000-0000-000000000013",
        "stop_loss": 485.0,
        "take_profit": 545.0,
    }
    sizing = {"size_usd": 50.0, "leverage": 1}

    await executor.execute_trade(signal, sizing)
    fake.place_order.assert_awaited_once()
    kwargs = fake.place_order.await_args.kwargs
    assert kwargs["side"] == "buy"
    assert kwargs["volume"] == round(50.0 / 510.0, 6)  # fractional preserved
