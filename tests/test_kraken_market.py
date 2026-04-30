"""Unit tests for kraken_market — universe filtering + caching."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from oracle.data_sources import kraken_market
from oracle.data_sources.kraken_market import (
    PairInfo,
    USD_QUOTES,
    clear_cache,
    discover_universe,
    fetch_ohlc,
)


_ASSET_PAIRS_FIXTURE: dict[str, dict[str, Any]] = {
    "XXBTZUSD": {
        "altname": "XBTUSD",
        "wsname": "XBT/USD",
        "base": "XXBT",
        "quote": "ZUSD",
        "leverage_buy": [2, 3, 4, 5],
        "leverage_sell": [2, 3, 4, 5],
        "lot_decimals": 8,
        "pair_decimals": 1,
        "ordermin": "0.0001",
        "status": "online",
    },
    "XETHZUSD": {
        "altname": "ETHUSD",
        "wsname": "ETH/USD",
        "base": "XETH",
        "quote": "ZUSD",
        "leverage_buy": [2, 3, 4, 5],
        "leverage_sell": [2, 3, 4, 5],
        "lot_decimals": 8,
        "pair_decimals": 2,
        "ordermin": "0.002",
        "status": "online",
    },
    "ADAUSD": {
        "altname": "ADAUSD",
        "wsname": "ADA/USD",
        "base": "ADA",
        "quote": "USD",
        "leverage_buy": [2, 3],
        "leverage_sell": [],
        "lot_decimals": 8,
        "pair_decimals": 6,
        "ordermin": "1",
        "status": "online",
    },
    "OFFLINEUSD": {
        "altname": "OFFLINEUSD",
        "wsname": "OFFLINE/USD",
        "base": "OFF",
        "quote": "USD",
        "leverage_buy": [],
        "leverage_sell": [],
        "lot_decimals": 8,
        "pair_decimals": 4,
        "ordermin": "1",
        "status": "delisted",
    },
    "XBTEUR": {
        "altname": "XBTEUR",
        "wsname": "XBT/EUR",
        "base": "XXBT",
        "quote": "ZEUR",
        "leverage_buy": [2, 3],
        "leverage_sell": [2, 3],
        "lot_decimals": 8,
        "pair_decimals": 1,
        "ordermin": "0.0001",
        "status": "online",
    },
}


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payloads: dict[str, dict]):
        self._payloads = payloads
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get(self, url: str, params: dict | None = None, timeout: float | None = None):
        self.calls.append((url, params))
        # Match by suffix
        for key, payload in self._payloads.items():
            if url.endswith(key):
                return _FakeResponse(payload)
        return _FakeResponse({"error": ["EUnknownAsset"], "result": {}}, status=200)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    # Reset the rate-limit clock so tests don't sleep
    kraken_market._last_call_at = 0.0
    yield
    clear_cache()


@pytest.fixture
def fake_assetpairs(monkeypatch):
    fake_payload = {"AssetPairs": {"error": [], "result": _ASSET_PAIRS_FIXTURE}}
    client = _FakeClient(fake_payload)

    def _factory(*args, **kwargs):
        return client

    monkeypatch.setattr(kraken_market.httpx, "AsyncClient", _factory)
    # Disable rate-limit pacing for fast tests
    monkeypatch.setattr(kraken_market, "RATE_LIMIT_MIN_GAP_SEC", 0.0)
    return client


async def test_discover_universe_filters_to_usd_online(fake_assetpairs):
    pairs = await discover_universe()
    altnames = {p.altname for p in pairs}
    # XBT/USD, ETH/USD, ADA/USD — all USD-quoted online
    assert "XBTUSD" in altnames
    assert "ETHUSD" in altnames
    assert "ADAUSD" in altnames
    # EUR pair filtered
    assert "XBTEUR" not in altnames
    # Offline pair filtered
    assert "OFFLINEUSD" not in altnames
    # All have valid quote
    for p in pairs:
        assert p.quote in USD_QUOTES
        assert p.status == "online"


async def test_discover_universe_caches(fake_assetpairs):
    # First call hits HTTP, second uses cache
    pairs1 = await discover_universe()
    pairs2 = await discover_universe()
    assert pairs1 == pairs2
    # Only one HTTP call
    assert len(fake_assetpairs.calls) == 1


async def test_discover_universe_force_refresh(fake_assetpairs):
    await discover_universe()
    await discover_universe(force_refresh=True)
    assert len(fake_assetpairs.calls) == 2


async def test_pair_info_shortable_flag(fake_assetpairs):
    pairs = await discover_universe()
    by_alt = {p.altname: p for p in pairs}
    assert by_alt["XBTUSD"].shortable is True
    assert by_alt["XBTUSD"].max_leverage_sell == 5
    # ADA has no leverage_sell — not shortable
    assert by_alt["ADAUSD"].shortable is False
    assert by_alt["ADAUSD"].longable_margin is True


async def test_fetch_ohlc_caches(monkeypatch):
    bars = [[1700000000, "65000", "65100", "64900", "65050", "65000", "10.5", 12]] * 5
    payload = {"OHLC": {"error": [], "result": {"XXBTZUSD": bars, "last": 1700000600}}}
    client = _FakeClient(payload)
    monkeypatch.setattr(kraken_market.httpx, "AsyncClient", lambda *a, **kw: client)
    monkeypatch.setattr(kraken_market, "RATE_LIMIT_MIN_GAP_SEC", 0.0)

    out1 = await fetch_ohlc("XXBTZUSD", interval=5)
    out2 = await fetch_ohlc("XXBTZUSD", interval=5)
    assert out1 == out2
    assert len(client.calls) == 1
    # All values coerced to float
    assert all(isinstance(v, float) for v in out1[0])


async def test_pair_info_dataclass_immutable():
    info = PairInfo(
        wsname="X/USD", base="X", quote="USD", altname="XUSD",
        leverage_buy=(2, 3), leverage_sell=(),
        lot_decimals=8, pair_decimals=4, ordermin=1.0,
    )
    with pytest.raises((AttributeError, Exception)):
        info.wsname = "Y/USD"  # type: ignore[misc]
    assert info.shortable is False
    assert info.longable_margin is True


async def test_kraken_error_response_raises(monkeypatch):
    payload = {"AssetPairs": {"error": ["EAPI:Rate limit exceeded"], "result": {}}}
    client = _FakeClient(payload)
    monkeypatch.setattr(kraken_market.httpx, "AsyncClient", lambda *a, **kw: client)
    monkeypatch.setattr(kraken_market, "RATE_LIMIT_MIN_GAP_SEC", 0.0)
    with pytest.raises(RuntimeError):
        await discover_universe(force_refresh=True)
