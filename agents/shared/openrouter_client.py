"""OpenRouter client — OpenAI-compatible API with retry and cost tracking."""
import asyncio
import logging
import time
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Approximate cost tracking (free models = $0, but track call counts)
_call_counts: dict[str, int] = {}
_call_today: dict[str, int] = {}


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, agent_id: str):
        self.api_key = api_key
        self.model = model
        self.agent_id = agent_id
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://atlas-trading.local",
                "X-Title": f"ATLAS-{agent_id}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        retries: int = 3,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "messages": messages if not system else [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        last_error = None
        for attempt in range(retries):
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                _call_counts[self.agent_id] = _call_counts.get(self.agent_id, 0) + 1
                return content
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("[%s] Rate limited, retrying in %ss", self.agent_id, wait)
                    await asyncio.sleep(wait)
                    last_error = e
                elif e.response.status_code >= 500:
                    await asyncio.sleep(2 ** attempt)
                    last_error = e
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("[%s] Connection error attempt %d: %s", self.agent_id, attempt, e)
                await asyncio.sleep(2 ** attempt)
                last_error = e

        raise RuntimeError(f"[{self.agent_id}] All {retries} attempts failed: {last_error}")

    async def stream(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages if not system else [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        import json
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue

    def get_call_count(self) -> int:
        return _call_counts.get(self.agent_id, 0)

    async def close(self) -> None:
        await self._client.aclose()
