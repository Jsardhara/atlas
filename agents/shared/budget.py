"""Per-day spend tracker for LLM-heavy operations.

Backed by Redis so multiple agents share the same daily ledger. Falls back
to an in-process dict if Redis is unreachable — single-agent dev still works
but the cap is best-effort.

Usage::

    tracker = BudgetTracker(redis, key_prefix="atlas:budget:tauric")
    if not await tracker.can_afford(estimated_cost_usd=0.30, daily_cap=5.0):
        return None
    await tracker.record(actual_cost_usd=0.27)

Daily ledger keys are scoped by UTC date so the cap rolls over at 00:00 UTC.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CAP_USD = 5.0


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class BudgetTracker:
    """Tracks USD spend per UTC day. Redis-backed; degrades to in-memory.

    The tracker does NOT bill anything — the caller is responsible for
    estimating cost before the call and reporting actuals after. The role
    of the tracker is to enforce the cap.
    """

    def __init__(
        self,
        redis: Any | None,
        key_prefix: str = "atlas:budget",
    ) -> None:
        self._redis = redis
        self._prefix = key_prefix
        self._fallback: dict[str, float] = {}

    def _key(self, date_str: str | None = None) -> str:
        return f"{self._prefix}:{date_str or _today_utc()}"

    async def spent_today(self) -> float:
        key = self._key()
        if self._redis is None:
            return float(self._fallback.get(key, 0.0))
        try:
            raw = await self._redis.get(key)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("budget.spent_today redis error, using fallback: %s", exc)
            return float(self._fallback.get(key, 0.0))
        return float(raw) if raw else 0.0

    async def can_afford(
        self,
        estimated_cost_usd: float,
        daily_cap: float = DEFAULT_CAP_USD,
    ) -> bool:
        """Return True if ``estimated_cost_usd`` would not breach the cap."""
        if daily_cap <= 0:
            return False
        if estimated_cost_usd < 0:
            return True
        spent = await self.spent_today()
        return (spent + estimated_cost_usd) <= daily_cap

    async def record(self, actual_cost_usd: float) -> float:
        """Add ``actual_cost_usd`` to today's ledger. Returns new total."""
        if actual_cost_usd <= 0:
            return await self.spent_today()
        key = self._key()
        if self._redis is None:
            new_total = float(self._fallback.get(key, 0.0)) + actual_cost_usd
            self._fallback[key] = new_total
            return new_total
        try:
            new_total_str = await self._redis.incrbyfloat(key, actual_cost_usd)
            # 36-hour TTL so yesterday's key disappears after rollover.
            await self._redis.expire(key, 60 * 60 * 36)
            return float(new_total_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning("budget.record redis error, using fallback: %s", exc)
            new_total = float(self._fallback.get(key, 0.0)) + actual_cost_usd
            self._fallback[key] = new_total
            return new_total


__all__ = ["BudgetTracker", "DEFAULT_CAP_USD"]
