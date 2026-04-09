"""Fetch FreqAI predictions from the running Freqtrade instance."""
import logging

import httpx

logger = logging.getLogger(__name__)


class FreqtradeClient:
    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self._auth = (username, password)

    async def get_status(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.url}/api/v1/status", auth=self._auth)
                return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.warning("Freqtrade status error: %s", e)
            return []

    async def get_profit(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.url}/api/v1/profit", auth=self._auth)
                return resp.json() if resp.status_code == 200 else {}
        except Exception as e:
            logger.warning("Freqtrade profit error: %s", e)
            return {}

    async def get_performance(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.url}/api/v1/performance", auth=self._auth)
                return resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.warning("Freqtrade performance error: %s", e)
            return []
