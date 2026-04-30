"""Kraken public market data — universe discovery + OHLC.

Public endpoints, no API key needed. Rate limited to ~1 RPS via async semaphore.
In-memory caches: universe TTL 1h, OHLC TTL 60s.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

KRAKEN_PUBLIC_BASE = "https://api.kraken.com/0/public"
USD_QUOTES = frozenset({"USD", "ZUSD"})
UNIVERSE_TTL_SEC = 3600
OHLC_TTL_SEC = 60
RATE_LIMIT_SEMAPHORE_SIZE = 1
RATE_LIMIT_MIN_GAP_SEC = 1.0
DEFAULT_TIMEOUT_SEC = 15


@dataclass(frozen=True)
class PairInfo:
    """Snapshot of a Kraken asset pair's tradability + sizing rules."""

    wsname: str
    base: str
    quote: str
    altname: str
    leverage_buy: tuple[int, ...]
    leverage_sell: tuple[int, ...]
    lot_decimals: int
    pair_decimals: int
    ordermin: float
    status: str = "online"

    @property
    def shortable(self) -> bool:
        return len(self.leverage_sell) > 0

    @property
    def longable_margin(self) -> bool:
        return len(self.leverage_buy) > 0

    @property
    def max_leverage_buy(self) -> int:
        return max(self.leverage_buy) if self.leverage_buy else 1

    @property
    def max_leverage_sell(self) -> int:
        return max(self.leverage_sell) if self.leverage_sell else 0


@dataclass
class _Cache:
    universe: list[PairInfo] | None = None
    universe_at: float = 0.0
    ohlc: dict[tuple[str, int], tuple[float, list[list[float]]]] = field(default_factory=dict)


_cache = _Cache()
_semaphore = asyncio.Semaphore(RATE_LIMIT_SEMAPHORE_SIZE)
_last_call_at: float = 0.0
_call_lock = asyncio.Lock()


def _coerce_leverage(value: Any) -> tuple[int, ...]:
    if not value:
        return ()
    try:
        return tuple(int(x) for x in value)
    except (TypeError, ValueError):
        return ()


def _parse_pair_info(altname: str, raw: dict[str, Any]) -> PairInfo | None:
    try:
        return PairInfo(
            wsname=raw.get("wsname", altname),
            base=raw.get("base", ""),
            quote=raw.get("quote", ""),
            altname=raw.get("altname", altname),
            leverage_buy=_coerce_leverage(raw.get("leverage_buy", [])),
            leverage_sell=_coerce_leverage(raw.get("leverage_sell", [])),
            lot_decimals=int(raw.get("lot_decimals", 8)),
            pair_decimals=int(raw.get("pair_decimals", 5)),
            ordermin=float(raw.get("ordermin", 0)),
            status=raw.get("status", "online"),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Failed parsing pair %s: %s", altname, exc)
        return None


async def _rate_limited_get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    """GET with global ~1 RPS pacing."""
    global _last_call_at
    async with _semaphore:
        async with _call_lock:
            now = time.monotonic()
            gap = now - _last_call_at
            if gap < RATE_LIMIT_MIN_GAP_SEC:
                await asyncio.sleep(RATE_LIMIT_MIN_GAP_SEC - gap)
            _last_call_at = time.monotonic()
        resp = await client.get(url, params=params, timeout=DEFAULT_TIMEOUT_SEC)
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"Kraken error: {body['error']}")
        return body.get("result", {})


async def discover_universe(force_refresh: bool = False) -> list[PairInfo]:
    """Return online USD-quoted pairs.

    Cached for 1h. Filters: quote in {USD, ZUSD}, status == online.
    """
    if (
        not force_refresh
        and _cache.universe is not None
        and (time.monotonic() - _cache.universe_at) < UNIVERSE_TTL_SEC
    ):
        return _cache.universe

    url = f"{KRAKEN_PUBLIC_BASE}/AssetPairs"
    async with httpx.AsyncClient() as client:
        result = await _rate_limited_get(client, url)

    pairs: list[PairInfo] = []
    for altname, raw in result.items():
        info = _parse_pair_info(altname, raw)
        if info is None:
            continue
        if info.quote not in USD_QUOTES:
            continue
        if info.status != "online":
            continue
        pairs.append(info)

    _cache.universe = pairs
    _cache.universe_at = time.monotonic()
    logger.info("Kraken universe loaded: %d USD pairs", len(pairs))
    return pairs


async def fetch_ohlc(
    pair: str,
    interval: int = 5,
    since: int | None = None,
) -> list[list[float]]:
    """Fetch OHLC bars for `pair`. Cached 60s when `since` is None.

    Returns list of bars: [time, open, high, low, close, vwap, volume, count].
    """
    cache_key = (pair, interval)
    if since is None:
        cached = _cache.ohlc.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < OHLC_TTL_SEC:
            return cached[1]

    url = f"{KRAKEN_PUBLIC_BASE}/OHLC"
    params: dict[str, Any] = {"pair": pair, "interval": interval}
    if since is not None:
        params["since"] = since

    async with httpx.AsyncClient() as client:
        result = await _rate_limited_get(client, url, params=params)

    bars: list[list[float]] = []
    for key, value in result.items():
        if key == "last":
            continue
        if isinstance(value, list):
            bars = [[float(x) for x in bar] for bar in value]
            break

    if since is None:
        _cache.ohlc[cache_key] = (time.monotonic(), bars)
    return bars


def clear_cache() -> None:
    """Test helper — wipe in-memory caches."""
    _cache.universe = None
    _cache.universe_at = 0.0
    _cache.ohlc.clear()
