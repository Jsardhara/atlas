"""Alpaca public market data — universe discovery + OHLC bars.

Public surface: ``PairInfo``, ``discover_universe``, ``fetch_ohlc``,
``clear_cache`` — consumed by Oracle ``agent.py`` and ``screener.py``.

Requires ``ALPACA_API_KEY`` + ``ALPACA_SECRET_KEY`` in env. The data
clients fall back to public IEX feed when keys are missing — bars still
come back, just with reduced rate limits.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

UNIVERSE_TTL_SEC = 3600
OHLC_TTL_SEC = 60


@dataclass(frozen=True)
class PairInfo:
    """Snapshot of a tradable symbol's metadata.

    Fields kept broker-agnostic so callers in `screener.py` don't care
    which data source provided them. ``leverage_buy`` / ``leverage_sell``
    are derived from Alpaca's marginable / shortable booleans.
    """

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
    ohlc: dict[tuple[str, int], tuple[float, list[list[float]]]] = field(
        default_factory=dict
    )


_cache = _Cache()


def _api_key() -> str:
    return os.environ.get("ALPACA_API_KEY", "")


def _secret_key() -> str:
    return os.environ.get("ALPACA_SECRET_KEY", "")


def _paper() -> bool:
    return os.environ.get("ALPACA_PAPER", "true").lower() in ("1", "true", "yes")


def _data_feed() -> str:
    return os.environ.get("ALPACA_DATA_FEED", "iex")


def _trading_client():
    from alpaca.trading.client import TradingClient

    return TradingClient(
        api_key=_api_key(),
        secret_key=_secret_key(),
        paper=_paper(),
    )


def _stock_data_client():
    from alpaca.data.historical.stock import StockHistoricalDataClient

    return StockHistoricalDataClient(api_key=_api_key(), secret_key=_secret_key())


def _crypto_data_client():
    from alpaca.data.historical.crypto import CryptoHistoricalDataClient

    return CryptoHistoricalDataClient(api_key=_api_key(), secret_key=_secret_key())


def _is_equity_symbol(symbol: str) -> bool:
    return "/" not in symbol


def _asset_to_pair_info(asset: Any) -> PairInfo | None:
    try:
        symbol = asset.symbol
        is_equity = _is_equity_symbol(symbol)
        base = symbol.split("/")[0] if "/" in symbol else symbol
        quote = symbol.split("/")[1] if "/" in symbol else "USD"
        # Alpaca equities → 1x cash, 4x intraday on margin accounts.
        if is_equity:
            buy_lev = (1, 4) if getattr(asset, "marginable", False) else (1,)
            sell_lev = (4,) if getattr(asset, "shortable", False) else ()
        else:
            # Crypto — Alpaca currently spot-only, no shorting.
            buy_lev = (1,)
            sell_lev = ()
        return PairInfo(
            wsname=symbol,
            base=base,
            quote=quote,
            altname=symbol.replace("/", ""),
            leverage_buy=buy_lev,
            leverage_sell=sell_lev,
            lot_decimals=8 if not is_equity else 0,
            pair_decimals=2 if is_equity else 5,
            ordermin=float(getattr(asset, "min_order_size", 0) or 0),
            status="online" if str(asset.status).split(".")[-1].lower() == "active" else "offline",
        )
    except (AttributeError, TypeError, ValueError) as exc:
        logger.warning("Failed parsing asset %s: %s", getattr(asset, "symbol", "?"), exc)
        return None


def _universe_whitelist() -> set[str]:
    """Parse ATLAS_UNIVERSE_WHITELIST env var into an upper-cased set.

    Empty value or unset → empty set (= no cap, legacy behavior).
    """
    raw = os.environ.get("ATLAS_UNIVERSE_WHITELIST", "")
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


async def discover_universe(force_refresh: bool = False) -> list[PairInfo]:
    """Return active US-equity + USD-quoted crypto pairs from Alpaca.

    When ``ATLAS_UNIVERSE_WHITELIST`` is set the result is capped to that
    set so the screener does not walk all ~13k tradable assets at the
    Alpaca rate-limit (which makes a single scan take hours).
    """
    if (
        not force_refresh
        and _cache.universe is not None
        and (time.monotonic() - _cache.universe_at) < UNIVERSE_TTL_SEC
    ):
        return _cache.universe

    try:
        from alpaca.trading.enums import AssetClass, AssetStatus
        from alpaca.trading.requests import GetAssetsRequest

        client = _trading_client()
        equities = await asyncio.to_thread(
            client.get_all_assets,
            filter=GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE,
            ),
        )
        cryptos = await asyncio.to_thread(
            client.get_all_assets,
            filter=GetAssetsRequest(
                asset_class=AssetClass.CRYPTO,
                status=AssetStatus.ACTIVE,
            ),
        )
    except Exception as exc:
        logger.error("Alpaca discover_universe error: %s", exc)
        return _cache.universe or []

    whitelist = _universe_whitelist()
    pairs: list[PairInfo] = []
    for asset in list(equities) + list(cryptos):
        info = _asset_to_pair_info(asset)
        if not info or info.status != "online" or not asset.tradable:
            continue
        if whitelist and info.wsname.upper() not in whitelist:
            continue
        pairs.append(info)

    _cache.universe = pairs
    _cache.universe_at = time.monotonic()
    logger.info(
        "Alpaca universe loaded: %d tradable assets (whitelist=%d)",
        len(pairs), len(whitelist),
    )
    return pairs


def _bars_dataframe_to_ohlc(df: Any, symbol: str) -> list[list[float]]:
    """Convert alpaca-py multi-index DataFrame → OHLC list-of-lists.

    Bar shape: [time, open, high, low, close, vwap, volume, count]
    """
    if df is None or df.empty:
        return []
    out: list[list[float]] = []
    for idx, row in df.iterrows():
        sym, ts = idx if isinstance(idx, tuple) else (symbol, idx)
        if sym != symbol:
            continue
        ts_unix = int(ts.timestamp())
        o = float(row["open"])
        h = float(row["high"])
        low = float(row["low"])
        c = float(row["close"])
        v = float(row["volume"])
        vw = float(row.get("vwap", c) if hasattr(row, "get") else c)
        n = int(row.get("trade_count", 0) if hasattr(row, "get") else 0)
        out.append([ts_unix, o, h, low, c, vw, v, n])
    return out


async def fetch_ohlc(
    pair: str,
    interval: int = 5,
    since: int | None = None,
) -> list[list[float]]:
    """Fetch OHLC bars for `pair`. Cached 60s when `since` is None.

    ``interval`` is in minutes. Returns OHLC bars (see ``_bars_dataframe_to_ohlc``).
    """
    cache_key = (pair, interval)
    if since is None:
        cached = _cache.ohlc.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < OHLC_TTL_SEC:
            return cached[1]

    try:
        from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        symbol = pair if "/" in pair or _is_equity_symbol(pair) else f"{pair[:-3]}/USD"
        is_equity = _is_equity_symbol(symbol)

        # Map minute interval → Alpaca TimeFrame
        if interval >= 1440:
            tf = TimeFrame(interval // 1440, TimeFrameUnit.Day)
        elif interval >= 60:
            tf = TimeFrame(interval // 60, TimeFrameUnit.Hour)
        else:
            tf = TimeFrame(max(1, interval), TimeFrameUnit.Minute)

        end = datetime.now(timezone.utc)
        if since is not None:
            start = datetime.fromtimestamp(since, tz=timezone.utc)
        else:
            # Window roughly fills 200 bars at the requested cadence.
            start = end - timedelta(minutes=interval * 200)

        if is_equity:
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=tf,
                start=start,
                end=end,
                feed=_data_feed(),
            )
            bars = await asyncio.to_thread(_stock_data_client().get_stock_bars, req)
        else:
            req = CryptoBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=tf,
                start=start,
                end=end,
            )
            bars = await asyncio.to_thread(_crypto_data_client().get_crypto_bars, req)

        ohlc_bars = _bars_dataframe_to_ohlc(bars.df, symbol)
    except Exception as exc:
        logger.error("Alpaca fetch_ohlc error for %s: %s", pair, exc)
        return []

    if since is None:
        _cache.ohlc[cache_key] = (time.monotonic(), ohlc_bars)
    return ohlc_bars


def clear_cache() -> None:
    """Test helper — wipe in-memory caches."""
    _cache.universe = None
    _cache.universe_at = 0.0
    _cache.ohlc.clear()
