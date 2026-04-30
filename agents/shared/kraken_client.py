"""Kraken REST API wrapper using python-kraken-sdk."""
import asyncio
import logging
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)


class KrakenClient:
    """Thin wrapper around python-kraken-sdk for spot/margin trading."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._spot = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from kraken.spot import Trade, User, Market
            self._trade = Trade(
                key=self.settings.kraken_api_key,
                secret=self.settings.kraken_api_secret,
            )
            self._user = User(
                key=self.settings.kraken_api_key,
                secret=self.settings.kraken_api_secret,
            )
            self._market = Market()
            logger.info("Kraken client initialised (demo=%s)", self.settings.kraken_use_demo)
        except ImportError:
            logger.warning("python-kraken-sdk not installed — Kraken client unavailable")
            self._trade = None

    async def get_balance(self) -> dict[str, float]:
        if not self._user:
            return {}
        try:
            result = await asyncio.to_thread(self._user.get_balance)
            return {k: float(v) for k, v in result.items()}
        except Exception as e:
            logger.error("Kraken get_balance error: %s", e)
            return {}

    async def get_open_orders(self) -> list[dict]:
        if not self._trade:
            return []
        try:
            result = await asyncio.to_thread(self._trade.get_open_orders)
            return list(result.get("open", {}).values())
        except Exception as e:
            logger.error("Kraken get_open_orders error: %s", e)
            return []

    async def place_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        volume: float,
        price: float | None = None,
        leverage: int = 1,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Place an order. validate=True for paper trading (no real execution)."""
        if not self._trade:
            return {"error": "Kraken client not available"}

        # Force validate=True unless live trading explicitly enabled
        if not self.settings.live_trading_enabled:
            validate = True

        params: dict[str, Any] = {
            "pair": pair,
            "type": side,
            "ordertype": order_type,
            "volume": str(volume),
            "validate": validate,
        }
        if price and order_type == "limit":
            params["price"] = str(price)
        if leverage > 1:
            params["leverage"] = str(leverage)

        try:
            result = await asyncio.to_thread(self._trade.create_order, **params)
            logger.info(
                "Order placed pair=%s side=%s vol=%s validate=%s result=%s",
                pair, side, volume, validate, result
            )
            return result
        except Exception as e:
            logger.error("Kraken place_order error: %s", e)
            return {"error": str(e)}

    async def cancel_order(self, order_id: str) -> dict:
        if not self._trade:
            return {}
        try:
            return await asyncio.to_thread(self._trade.cancel_order, txid=order_id)
        except Exception as e:
            logger.error("Kraken cancel_order error: %s", e)
            return {"error": str(e)}

    async def get_asset_pairs(self) -> dict:
        """Public AssetPairs endpoint. Used for universe discovery and shortable
        check by Guardian."""
        try:
            from kraken.spot import Market
            market = Market()
            result = await asyncio.to_thread(market.get_asset_pairs)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error("Kraken get_asset_pairs error: %s", e)
            return {}

    async def get_ticker(self, pair: str) -> dict:
        try:
            from kraken.spot import Market
            market = Market()
            result = await asyncio.to_thread(market.get_ticker, pair=pair)
            return result.get(pair, {})
        except Exception as e:
            logger.error("Kraken get_ticker error: %s", e)
            return {}

    async def get_trade_history(self, start: int | None = None) -> list[dict]:
        if not self._trade:
            return []
        try:
            params = {}
            if start:
                params["start"] = start
            result = await asyncio.to_thread(self._trade.get_trades_history, **params)
            return list(result.get("trades", {}).values())
        except Exception as e:
            logger.error("Kraken trade history error: %s", e)
            return []
