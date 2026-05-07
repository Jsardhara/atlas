"""Alpaca REST API wrapper using alpaca-py.

Coroutine-shaped surface used by Trader and Oracle. Return shapes are
flat dicts so callers stay broker-agnostic.

Pairs are normalized to Alpaca symbols on the way in:
    "BTC/USD" → crypto symbol "BTC/USD"
    "AAPL"    → equity symbol "AAPL"
    "BTCUSD"  → crypto symbol "BTC/USD" (legacy altname)

Paper vs live is controlled by Settings.alpaca_paper. Settings.live_trading_enabled
gates real submission — when off, orders are submitted to the paper account.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)

# Equities are 1-5 char uppercase symbols. Anything else routed as crypto.
_EQUITY_HINT_LEN = 5


def _normalize_symbol(pair: str) -> tuple[str, str]:
    """Return (alpaca_symbol, asset_class) where asset_class ∈ {'crypto','equity'}.

    Rules (in order):
      1. Contains '/' → crypto (e.g. BTC/USD, ETH/USDT)
      2. Ends in USD/USDT/USDC + longer than suffix → crypto altname → split it
      3. Pure alpha, ≤ 5 chars → equity (AAPL, MSFT)
      4. Default → crypto
    """
    pair = pair.upper().strip()
    if "/" in pair:
        return pair, "crypto"
    if pair.endswith("USD") and len(pair) > 3 and pair[:-3].isalpha():
        return f"{pair[:-3]}/USD", "crypto"
    if pair.endswith("USDT") and len(pair) > 4 and pair[:-4].isalpha():
        return f"{pair[:-4]}/USDT", "crypto"
    if pair.endswith("USDC") and len(pair) > 4 and pair[:-4].isalpha():
        return f"{pair[:-4]}/USDC", "crypto"
    if pair.isalpha() and len(pair) <= _EQUITY_HINT_LEN:
        return pair, "equity"
    return pair, "crypto"


def _is_equity_symbol(pair: str) -> bool:
    return _normalize_symbol(pair)[1] == "equity"


class AlpacaClient:
    """Thin async wrapper over alpaca-py TradingClient + data clients."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._trading: Any = None
        self._stock_data: Any = None
        self._crypto_data: Any = None
        self._init_clients()

    def _init_clients(self) -> None:
        try:
            from alpaca.data.historical.crypto import CryptoHistoricalDataClient
            from alpaca.data.historical.stock import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient

            self._trading = TradingClient(
                api_key=self.settings.alpaca_api_key,
                secret_key=self.settings.alpaca_secret_key,
                paper=self.settings.alpaca_paper,
            )
            # Data clients work without auth for IEX equity feed; auth boosts limits.
            self._stock_data = StockHistoricalDataClient(
                api_key=self.settings.alpaca_api_key,
                secret_key=self.settings.alpaca_secret_key,
            )
            self._crypto_data = CryptoHistoricalDataClient(
                api_key=self.settings.alpaca_api_key,
                secret_key=self.settings.alpaca_secret_key,
            )
            logger.info(
                "Alpaca client initialised (paper=%s feed=%s)",
                self.settings.alpaca_paper,
                self.settings.alpaca_data_feed,
            )
        except ImportError:
            logger.warning("alpaca-py not installed — Alpaca client unavailable")
            self._trading = None

    # ── Account / balance ────────────────────────────────────────────────

    async def get_balance(self) -> dict[str, float]:
        """Return cash + position-level balances keyed by asset symbol.

        Flat dict shape: ``{"USD": cash, "<SYM>": qty, ...}``.
        """
        if not self._trading:
            return {}
        try:
            import asyncio

            account = await asyncio.to_thread(self._trading.get_account)
            out: dict[str, float] = {"USD": float(account.cash)}
            positions = await asyncio.to_thread(self._trading.get_all_positions)
            for pos in positions:
                out[pos.symbol] = float(pos.qty)
            return out
        except Exception as exc:
            logger.error("Alpaca get_balance error: %s", exc)
            return {}

    async def get_open_orders(self) -> list[dict]:
        if not self._trading:
            return []
        try:
            import asyncio

            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100)
            orders = await asyncio.to_thread(self._trading.get_orders, filter=req)
            return [self._order_to_dict(o) for o in orders]
        except Exception as exc:
            logger.error("Alpaca get_open_orders error: %s", exc)
            return []

    # ── Orders ───────────────────────────────────────────────────────────

    async def place_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        volume: float,
        price: float | None = None,
        leverage: int = 1,  # noqa: ARG002 — Alpaca handles margin server-side
        validate: bool = True,
    ) -> dict[str, Any]:
        """Place an order. Returns flat dict ``{txid, descr, ...}``.

        ``validate=True`` is a dry-run — we skip submission entirely and return a
        synthetic txid. When ``validate=False`` AND ``live_trading_enabled`` AND
        ``alpaca_paper=False``, hits the live broker.
        """
        if not self._trading:
            return {"error": "Alpaca client not available"}

        # Hard safety: refuse live if not enabled at config level.
        if not self.settings.live_trading_enabled:
            validate = True

        symbol, asset_class = _normalize_symbol(pair)

        if validate:
            # Dry-run: log intent, return synthetic txid.
            fake_id = f"paper-{datetime.now(timezone.utc).timestamp():.0f}"
            logger.info(
                "Order dry-run: %s %s vol=%s asset=%s id=%s",
                side, symbol, volume, asset_class, fake_id,
            )
            return {"txid": [fake_id], "descr": {"order": "validate-only"}}

        try:
            import asyncio

            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import (
                LimitOrderRequest,
                MarketOrderRequest,
            )

            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.GTC if asset_class == "crypto" else TimeInForce.DAY

            if order_type == "limit" and price:
                req = LimitOrderRequest(
                    symbol=symbol,
                    qty=volume,
                    side=order_side,
                    time_in_force=tif,
                    limit_price=float(price),
                )
            else:
                req = MarketOrderRequest(
                    symbol=symbol,
                    qty=volume,
                    side=order_side,
                    time_in_force=tif,
                )

            order = await asyncio.to_thread(self._trading.submit_order, order_data=req)
            return {
                "txid": [str(order.id)],
                "descr": {"order": f"{side} {volume} {symbol} @ {order_type}"},
                "order": self._order_to_dict(order),
            }
        except Exception as exc:
            logger.error("Alpaca place_order error: %s", exc)
            return {"error": str(exc)}

    async def cancel_order(self, order_id: str) -> dict:
        if not self._trading:
            return {}
        try:
            import asyncio

            await asyncio.to_thread(self._trading.cancel_order_by_id, order_id)
            return {"count": 1}
        except Exception as exc:
            logger.error("Alpaca cancel_order error: %s", exc)
            return {"error": str(exc)}

    # ── Market data ──────────────────────────────────────────────────────

    async def get_asset(self, symbol: str) -> dict:
        """Return live attributes for one symbol: tradable, shortable,
        easy_to_borrow, marginable, fractionable. Empty dict on failure.

        Live (not cached) — Alpaca refreshes ETB nightly so callers should
        re-check before each SHORT submission.
        """
        if not self._trading:
            return {}
        try:
            import asyncio
            asset = await asyncio.to_thread(self._trading.get_asset, symbol)
            return {
                "symbol": asset.symbol,
                "tradable": bool(asset.tradable),
                "shortable": bool(getattr(asset, "shortable", False)),
                "easy_to_borrow": bool(getattr(asset, "easy_to_borrow", False)),
                "marginable": bool(getattr(asset, "marginable", False)),
                "fractionable": bool(getattr(asset, "fractionable", False)),
                "asset_class": str(asset.asset_class).split(".")[-1].lower(),
            }
        except Exception as exc:
            logger.error("Alpaca get_asset(%s) error: %s", symbol, exc)
            return {}

    async def get_asset_pairs(self) -> dict:
        """Return ``{alpaca_symbol: {altname, base, quote, shortable, ...}}``.

        Used by Guardian for shortable check + universe discovery.
        """
        if not self._trading:
            return {}
        try:
            import asyncio

            from alpaca.trading.enums import AssetClass, AssetStatus
            from alpaca.trading.requests import GetAssetsRequest

            req = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE,
            )
            equities = await asyncio.to_thread(self._trading.get_all_assets, filter=req)
            crypto_req = GetAssetsRequest(
                asset_class=AssetClass.CRYPTO,
                status=AssetStatus.ACTIVE,
            )
            cryptos = await asyncio.to_thread(self._trading.get_all_assets, filter=crypto_req)

            out: dict[str, dict] = {}
            for a in list(equities) + list(cryptos):
                altname = a.symbol.replace("/", "")
                out[a.symbol] = {
                    "altname": altname,
                    "base": (a.symbol.split("/")[0] if "/" in a.symbol else a.symbol),
                    "quote": (a.symbol.split("/")[1] if "/" in a.symbol else "USD"),
                    "tradable": bool(a.tradable),
                    "shortable": bool(getattr(a, "shortable", False)),
                    "marginable": bool(getattr(a, "marginable", False)),
                    "asset_class": str(a.asset_class).split(".")[-1].lower(),
                }
            return out
        except Exception as exc:
            logger.error("Alpaca get_asset_pairs error: %s", exc)
            return {}

    async def get_ticker(self, pair: str) -> dict:
        """Return ticker dict ``{'c': [last_price, ...], ...}``.

        Callers index ``ticker.get("c", [0])[0]`` so we honor that layout.
        """
        symbol, asset_class = _normalize_symbol(pair)
        try:
            import asyncio

            if asset_class == "crypto":
                from alpaca.data.requests import CryptoLatestQuoteRequest

                req = CryptoLatestQuoteRequest(symbol_or_symbols=[symbol])
                quotes = await asyncio.to_thread(
                    self._crypto_data.get_crypto_latest_quote, req
                )
                quote = quotes.get(symbol)
                if quote is None:
                    return {}
                last = float(quote.ask_price or quote.bid_price or 0)
                return {"c": [str(last)], "b": [str(quote.bid_price or 0)],
                        "a": [str(quote.ask_price or 0)]}

            from alpaca.data.requests import StockLatestQuoteRequest

            req = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
            quotes = await asyncio.to_thread(
                self._stock_data.get_stock_latest_quote, req
            )
            quote = quotes.get(symbol)
            if quote is None:
                return {}
            last = float(quote.ask_price or quote.bid_price or 0)
            return {"c": [str(last)], "b": [str(quote.bid_price or 0)],
                    "a": [str(quote.ask_price or 0)]}
        except Exception as exc:
            logger.error("Alpaca get_ticker error for %s: %s", pair, exc)
            return {}

    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str = "1Hour",
        lookback_hours: int = 24,
    ) -> list[dict]:
        """Return OHLCV bars — used by Oracle market scan.

        timeframe accepts Alpaca format ("1Min", "5Min", "1Hour", "1Day").
        Returns [{ts, open, high, low, close, volume}, ...] newest last.
        """
        symbol, asset_class = _normalize_symbol(pair)
        try:
            import asyncio

            from alpaca.data.requests import (
                CryptoBarsRequest,
                StockBarsRequest,
            )

            tf = _parse_timeframe(timeframe)
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=lookback_hours)

            if asset_class == "crypto":
                req = CryptoBarsRequest(
                    symbol_or_symbols=[symbol],
                    timeframe=tf,
                    start=start,
                    end=end,
                )
                bars = await asyncio.to_thread(
                    self._crypto_data.get_crypto_bars, req
                )
            else:
                req = StockBarsRequest(
                    symbol_or_symbols=[symbol],
                    timeframe=tf,
                    start=start,
                    end=end,
                    feed=self.settings.alpaca_data_feed,
                )
                bars = await asyncio.to_thread(self._stock_data.get_stock_bars, req)

            df = bars.df  # multiindex (symbol, timestamp)
            out: list[dict] = []
            if df is None or df.empty:
                return out
            for (sym, ts), row in df.iterrows():  # type: ignore[misc]
                if sym != symbol:
                    continue
                out.append(
                    {
                        "ts": int(ts.timestamp()),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    }
                )
            return out
        except Exception as exc:
            logger.error("Alpaca get_ohlcv error for %s: %s", pair, exc)
            return []

    async def get_trade_history(self, start: int | None = None) -> list[dict]:
        """Closed orders, newest first. Minimal flat-dict projection."""
        if not self._trading:
            return []
        try:
            import asyncio

            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus

            after = (
                datetime.fromtimestamp(start, tz=timezone.utc)
                if start
                else datetime.now(timezone.utc) - timedelta(days=30)
            )
            req = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=after,
                limit=100,
            )
            orders = await asyncio.to_thread(self._trading.get_orders, filter=req)
            return [self._order_to_dict(o) for o in orders]
        except Exception as exc:
            logger.error("Alpaca trade history error: %s", exc)
            return []

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _order_to_dict(order: Any) -> dict:
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "side": str(order.side).split(".")[-1].lower(),
            "qty": float(order.qty) if order.qty else 0.0,
            "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
            "filled_avg_price": (
                float(order.filled_avg_price) if order.filled_avg_price else None
            ),
            "status": str(order.status).split(".")[-1].lower(),
            "type": str(order.order_type).split(".")[-1].lower(),
            "submitted_at": (
                order.submitted_at.isoformat() if order.submitted_at else None
            ),
        }


def _parse_timeframe(s: str) -> Any:
    """Map a string like '1Hour' or '5Min' to alpaca-py TimeFrame."""
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    s = s.strip()
    digits = "".join(c for c in s if c.isdigit()) or "1"
    unit_token = "".join(c for c in s if c.isalpha()).lower()
    unit_map = {
        "min": TimeFrameUnit.Minute,
        "minute": TimeFrameUnit.Minute,
        "hour": TimeFrameUnit.Hour,
        "h": TimeFrameUnit.Hour,
        "day": TimeFrameUnit.Day,
        "d": TimeFrameUnit.Day,
        "week": TimeFrameUnit.Week,
        "month": TimeFrameUnit.Month,
    }
    unit = unit_map.get(unit_token, TimeFrameUnit.Hour)
    return TimeFrame(int(digits), unit)
