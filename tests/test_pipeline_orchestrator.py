"""Tests for ``api/pipeline_orchestrator.py``.

Decision logic is exercised as a pure function. Stream-side behaviour
(idempotency, advance/block emission) uses an in-memory FakeRedis plus a
hand-rolled session factory that returns canned portfolio + agent rows.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from api.pipeline_orchestrator import (
    PipelineOrchestrator,
    PortfolioGate,
    STREAM_KEY,
    _decide,
)
from tests._fakes import FakeRedis


# ── pure decision logic ──────────────────────────────────────────────────


def test_decide_advances_on_clean_state() -> None:
    snap = PortfolioGate(0, 0.0, frozenset())
    decision, _ = _decide(snap, target_agent="guardian", daily_loss_limit_usd=50, max_concurrent=5)
    assert decision == "advance"


def test_decide_blocks_when_loss_limit_exceeded() -> None:
    snap = PortfolioGate(0, -100.0, frozenset())
    decision, reason = _decide(snap, target_agent="guardian", daily_loss_limit_usd=50, max_concurrent=5)
    assert decision == "block"
    assert "loss limit" in reason


def test_decide_blocks_at_max_concurrent() -> None:
    snap = PortfolioGate(5, 0.0, frozenset())
    decision, reason = _decide(snap, target_agent="guardian", daily_loss_limit_usd=50, max_concurrent=5)
    assert decision == "block"
    assert "max_concurrent" in reason


def test_decide_blocks_when_target_paused() -> None:
    snap = PortfolioGate(0, 0.0, frozenset({"guardian"}))
    decision, reason = _decide(snap, target_agent="guardian", daily_loss_limit_usd=50, max_concurrent=5)
    assert decision == "block"
    assert "paused" in reason


# ── stream emission ──────────────────────────────────────────────────────


class _FakeRow:
    def __init__(self, **kw: Any) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeResult:
    def __init__(self, scalar: Any = None, rows: list[_FakeRow] | None = None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self) -> Any:
        return self._scalar

    def fetchall(self) -> list[_FakeRow]:
        return self._rows


class _FakeSession:
    def __init__(
        self,
        open_count: int = 0,
        daily_pnl: float = 0.0,
        paused: list[str] | None = None,
        stale_agents: list[tuple[str, datetime | None]] | None = None,
    ) -> None:
        self.open_count = open_count
        self.daily_pnl = daily_pnl
        self.paused = paused or []
        self.stale_agents = stale_agents or []
        self._call = 0

    async def execute(self, stmt, params: dict | None = None) -> _FakeResult:
        sql = str(stmt).lower()
        if "from trades" in sql and "count" in sql:
            return _FakeResult(scalar=self.open_count)
        if "from trades" in sql and "sum(pnl_usd)" in sql:
            return _FakeResult(scalar=self.daily_pnl)
        if "where state = 'paused'" in sql:
            return _FakeResult(rows=[_FakeRow(id=a) for a in self.paused])
        if "from agents" in sql and "last_heartbeat" in sql:
            return _FakeResult(
                rows=[_FakeRow(id=a, last_heartbeat=hb) for a, hb in self.stale_agents]
            )
        return _FakeResult()


def _session_factory(session: _FakeSession):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


def _run(coro: Any) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


def test_handle_signal_emits_advance_on_clean_state(fake_redis: FakeRedis) -> None:
    sess = _FakeSession()
    orch = PipelineOrchestrator(
        fake_redis,
        _session_factory(sess),  # type: ignore[arg-type]
        daily_loss_limit_usd=50,
        max_concurrent=5,
    )
    emitted = _run(orch.handle_signal_payload({"signal_id": "s-1"}))
    assert emitted is True

    msgs = fake_redis._streams[STREAM_KEY]
    assert len(msgs) == 1
    payload = json.loads(msgs[0][1]["json"])
    assert payload["message_type"] == "pipeline_decision"
    assert payload["payload"]["decision"] == "advance"
    assert payload["correlation_id"] == "s-1"


def test_handle_signal_blocks_when_loss_limit_exceeded(fake_redis: FakeRedis) -> None:
    sess = _FakeSession(daily_pnl=-200.0)
    orch = PipelineOrchestrator(
        fake_redis,
        _session_factory(sess),  # type: ignore[arg-type]
        daily_loss_limit_usd=50,
        max_concurrent=5,
    )
    _run(orch.handle_signal_payload({"signal_id": "s-2"}))
    payload = json.loads(fake_redis._streams[STREAM_KEY][0][1]["json"])
    assert payload["payload"]["decision"] == "block"
    assert "loss limit" in payload["payload"]["reason"]


def test_handle_signal_is_idempotent_on_duplicate_id(fake_redis: FakeRedis) -> None:
    sess = _FakeSession()
    orch = PipelineOrchestrator(
        fake_redis,
        _session_factory(sess),  # type: ignore[arg-type]
        daily_loss_limit_usd=50,
        max_concurrent=5,
    )
    first = _run(orch.handle_signal_payload({"signal_id": "dup"}))
    second = _run(orch.handle_signal_payload({"signal_id": "dup"}))
    assert first is True
    assert second is False
    assert len(fake_redis._streams[STREAM_KEY]) == 1


def test_handle_signal_without_signal_id_is_noop(fake_redis: FakeRedis) -> None:
    sess = _FakeSession()
    orch = PipelineOrchestrator(
        fake_redis,
        _session_factory(sess),  # type: ignore[arg-type]
    )
    assert _run(orch.handle_signal_payload({})) is False
    assert STREAM_KEY not in fake_redis._streams or not fake_redis._streams[STREAM_KEY]


def test_heartbeat_pass_emits_for_stale_agents(fake_redis: FakeRedis) -> None:
    long_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    sess = _FakeSession(stale_agents=[("oracle", long_ago), ("trader", None)])
    orch = PipelineOrchestrator(
        fake_redis,
        _session_factory(sess),  # type: ignore[arg-type]
    )
    count = _run(orch.emit_heartbeat_pass())
    assert count == 2

    msgs = fake_redis._streams[STREAM_KEY]
    assert len(msgs) == 2
    types = {json.loads(m[1]["json"])["message_type"] for m in msgs}
    assert types == {"agent_status"}
