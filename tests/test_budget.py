"""Tests for ``agents/shared/budget.py`` — daily LLM-spend tracker."""

from __future__ import annotations

import pytest

from shared.budget import BudgetTracker  # type: ignore[import-not-found]
from tests._fakes import FakeRedis


@pytest.mark.asyncio
async def test_can_afford_below_cap():
    tracker = BudgetTracker(FakeRedis(), key_prefix="t1")
    assert await tracker.can_afford(estimated_cost_usd=0.5, daily_cap=5.0)


@pytest.mark.asyncio
async def test_can_afford_exact_cap_is_ok():
    tracker = BudgetTracker(FakeRedis(), key_prefix="t1b")
    assert await tracker.can_afford(estimated_cost_usd=5.0, daily_cap=5.0)


@pytest.mark.asyncio
async def test_record_accumulates_and_blocks_when_cap_breached():
    tracker = BudgetTracker(FakeRedis(), key_prefix="t2")
    await tracker.record(2.0)
    await tracker.record(2.0)
    assert await tracker.can_afford(estimated_cost_usd=0.5, daily_cap=5.0)
    await tracker.record(1.5)
    assert not await tracker.can_afford(estimated_cost_usd=0.5, daily_cap=5.0)


@pytest.mark.asyncio
async def test_zero_or_negative_cap_blocks_everything():
    tracker = BudgetTracker(FakeRedis(), key_prefix="t3")
    assert not await tracker.can_afford(estimated_cost_usd=0.01, daily_cap=0.0)
    assert not await tracker.can_afford(estimated_cost_usd=0.01, daily_cap=-1.0)


@pytest.mark.asyncio
async def test_negative_estimated_cost_is_free():
    tracker = BudgetTracker(FakeRedis(), key_prefix="t4")
    assert await tracker.can_afford(estimated_cost_usd=-0.5, daily_cap=1.0)


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_in_memory_ledger():
    """If Redis blows up, the tracker degrades to a process-local dict
    (best-effort cap, never raises)."""

    class BrokenRedis:
        async def get(self, key: str) -> None:
            raise RuntimeError("redis down")

        async def incrbyfloat(self, key: str, val: float) -> str:
            raise RuntimeError("redis down")

        async def expire(self, key: str, ttl: int) -> bool:
            raise RuntimeError("redis down")

    tracker = BudgetTracker(BrokenRedis(), key_prefix="t5")
    total = await tracker.record(0.75)
    assert total == 0.75
    spent = await tracker.spent_today()
    assert spent == 0.75


@pytest.mark.asyncio
async def test_no_redis_uses_in_memory_only():
    tracker = BudgetTracker(None, key_prefix="t6")
    await tracker.record(1.25)
    assert await tracker.spent_today() == 1.25
