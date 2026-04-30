"""Deterministic pipeline orchestrator (no LLM).

Replaces the deleted Commander agent. Runs as a long-lived asyncio task
inside the FastAPI lifespan. Two responsibilities:

1. **Signal gating** — consumes ``MARKET_SIGNAL`` events from the
   ``atlas:events`` Redis stream, reads portfolio state from Postgres, and
   emits a ``PIPELINE_DECISION`` (advance / block) so Guardian can proceed
   or halt.
2. **Heartbeat watchdog** — every 30 s, scans the ``agents`` table and
   emits an ``AGENT_STATUS`` event for any agent whose ``last_heartbeat``
   is older than 60 s.

Idempotent on duplicate ``signal_id`` via Redis ``SET orch:seen:<id> 1 EX
300 NX``. Pure stdlib + asyncpg/redis — never imports an LLM client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Pipeline orchestrator runs in-process with the API; reuse the agents-side
# protocols + settings (added to sys.path by `agents/` Dockerfile and
# `tests/conftest.py`).
from shared.config import get_settings  # type: ignore[import-not-found]
from shared.protocols import (  # type: ignore[import-not-found]
    AgentID,
    AtlasMessage,
    MessageType,
)

logger = logging.getLogger(__name__)

STREAM_KEY = "atlas:events"
CONSUMER_GROUP = "orchestrator"
CONSUMER_NAME = "orchestrator-1"
HEARTBEAT_INTERVAL_SEC = 30
HEARTBEAT_STALE_SEC = 60
SIGNAL_DEDUP_TTL_SEC = 300
DEFAULT_MAX_CONCURRENT = 5


@dataclass(frozen=True)
class PortfolioGate:
    """Snapshot of state used to gate signals."""

    open_position_count: int
    daily_pnl_usd: float
    paused_agent_ids: frozenset[str]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _publish(redis: aioredis.Redis, msg: AtlasMessage) -> None:
    """Append one message to the Atlas event stream."""
    await redis.xadd(STREAM_KEY, {"json": msg.model_dump_json()})


async def _ensure_group(redis: aioredis.Redis) -> None:
    """Create the consumer group on first run (idempotent)."""
    try:
        await redis.xgroup_create(
            STREAM_KEY, CONSUMER_GROUP, id="$", mkstream=True
        )
    except Exception as exc:  # noqa: BLE001 — group already exists is fine
        if "BUSYGROUP" not in str(exc):
            logger.warning("xgroup_create failed: %s", exc)


def _decide(
    snapshot: PortfolioGate,
    target_agent: str | None,
    daily_loss_limit_usd: float,
    max_concurrent: int,
) -> tuple[str, str]:
    """Pure decision: returns (decision, reason)."""
    if snapshot.daily_pnl_usd <= -abs(daily_loss_limit_usd):
        return "block", (
            f"daily_pnl {snapshot.daily_pnl_usd:.2f} usd exceeded "
            f"loss limit {daily_loss_limit_usd:.2f}"
        )
    if snapshot.open_position_count >= max_concurrent:
        return "block", (
            f"open_positions {snapshot.open_position_count} "
            f">= max_concurrent {max_concurrent}"
        )
    if target_agent and target_agent in snapshot.paused_agent_ids:
        return "block", f"agent {target_agent} is paused"
    return "advance", "ok"


async def _read_portfolio_gate(session: AsyncSession) -> PortfolioGate:
    """Snapshot portfolio + agent pause state for gating."""
    open_count_row = await session.execute(
        text(
            "SELECT COUNT(*) AS n FROM trades "
            "WHERE status = 'open' AND is_paper = true"
        )
    )
    open_count = int(open_count_row.scalar() or 0)

    pnl_row = await session.execute(
        text(
            "SELECT COALESCE(SUM(pnl_usd), 0) AS p FROM trades "
            "WHERE closed_at >= :since AND is_paper = true"
        ),
        {"since": _now_utc() - timedelta(hours=24)},
    )
    daily_pnl = float(pnl_row.scalar() or 0.0)

    paused_rows = await session.execute(
        text("SELECT id FROM agents WHERE state = 'paused'")
    )
    paused = frozenset(str(r.id) for r in paused_rows.fetchall())

    return PortfolioGate(
        open_position_count=open_count,
        daily_pnl_usd=daily_pnl,
        paused_agent_ids=paused,
    )


async def _list_stale_agents(session: AsyncSession) -> list[tuple[str, datetime | None]]:
    """Return ``(agent_id, last_heartbeat)`` rows whose heartbeat is stale."""
    cutoff = _now_utc() - timedelta(seconds=HEARTBEAT_STALE_SEC)
    result = await session.execute(
        text(
            "SELECT id, last_heartbeat FROM agents "
            "WHERE last_heartbeat IS NULL OR last_heartbeat < :cutoff"
        ),
        {"cutoff": cutoff},
    )
    return [(str(r.id), r.last_heartbeat) for r in result.fetchall()]


class PipelineOrchestrator:
    """Long-lived background service. Spawn via :meth:`start`, stop via :meth:`stop`."""

    def __init__(
        self,
        redis: aioredis.Redis,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        daily_loss_limit_usd: float | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self._redis = redis
        self._session_factory = session_factory
        settings = get_settings()
        self._daily_loss_limit_usd = (
            daily_loss_limit_usd
            if daily_loss_limit_usd is not None
            else float(settings.daily_loss_limit_usd)
        )
        self._max_concurrent = max_concurrent
        self._signal_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        await _ensure_group(self._redis)
        self._signal_task = asyncio.create_task(
            self._signal_loop(), name="orchestrator-signals"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="orchestrator-heartbeats"
        )
        logger.info("PipelineOrchestrator started")

    async def stop(self) -> None:
        self._stop_event.set()
        for task in (self._signal_task, self._heartbeat_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        logger.info("PipelineOrchestrator stopped")

    # ── public hooks (used by tests) ───────────────────────────────────────

    async def handle_signal_payload(self, payload: dict[str, Any]) -> bool:
        """Process one ``MARKET_SIGNAL`` payload. Returns True if a decision
        was emitted, False if the signal was a duplicate (deduped)."""
        signal_id = str(payload.get("signal_id") or "")
        if not signal_id:
            logger.warning("MARKET_SIGNAL missing signal_id, ignoring")
            return False

        dedup_key = f"orch:seen:{signal_id}"
        reserved = await self._redis.set(
            dedup_key, "1", ex=SIGNAL_DEDUP_TTL_SEC, nx=True
        )
        if not reserved:
            logger.info("Duplicate MARKET_SIGNAL %s — skipped", signal_id)
            return False

        async with self._session_factory() as sess:
            snapshot = await _read_portfolio_gate(sess)

        target_agent = payload.get("target_agent") or AgentID.GUARDIAN.value
        decision, reason = _decide(
            snapshot,
            target_agent=target_agent,
            daily_loss_limit_usd=self._daily_loss_limit_usd,
            max_concurrent=self._max_concurrent,
        )

        msg = AtlasMessage(
            source_agent=AgentID.SYSTEM,
            target_agent=AgentID.GUARDIAN,
            message_type=MessageType.PIPELINE_DECISION,
            correlation_id=signal_id,
            payload={
                "signal_id": signal_id,
                "decision": decision,
                "reason": reason,
                "open_positions": snapshot.open_position_count,
                "daily_pnl_usd": snapshot.daily_pnl_usd,
            },
        )
        await _publish(self._redis, msg)
        return True

    async def emit_heartbeat_pass(self) -> int:
        """Single sweep of the heartbeat watchdog. Returns count of stale
        agents reported."""
        async with self._session_factory() as sess:
            stale = await _list_stale_agents(sess)

        for agent_id, last_hb in stale:
            msg = AtlasMessage(
                source_agent=AgentID.SYSTEM,
                target_agent=None,
                message_type=MessageType.AGENT_STATUS,
                payload={
                    "agent_id": agent_id,
                    "state": "stale_heartbeat",
                    "last_heartbeat": last_hb.isoformat() if last_hb else None,
                    "stale_threshold_sec": HEARTBEAT_STALE_SEC,
                },
                priority=4,
            )
            await _publish(self._redis, msg)
        return len(stale)

    # ── internal loops ─────────────────────────────────────────────────────

    async def _signal_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                resp = await self._redis.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=10,
                    block=1000,
                )
                if not resp:
                    continue
                for _stream, messages in resp:
                    for msg_id, fields in messages:
                        try:
                            data = json.loads(fields.get("json", "{}"))
                        except (ValueError, TypeError):
                            await self._redis.xack(
                                STREAM_KEY, CONSUMER_GROUP, msg_id
                            )
                            continue
                        if data.get("message_type") == MessageType.MARKET_SIGNAL.value:
                            await self.handle_signal_payload(
                                data.get("payload", {})
                            )
                        await self._redis.xack(
                            STREAM_KEY, CONSUMER_GROUP, msg_id
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 — keep loop alive
                logger.warning("orchestrator signal loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.emit_heartbeat_pass()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 — keep loop alive
                logger.warning("heartbeat loop error: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
                continue


__all__ = [
    "PipelineOrchestrator",
    "PortfolioGate",
    "STREAM_KEY",
    "_decide",
]


# Module-level helper kept for tests that prefer instantiating without the API.
def make_orchestrator(
    redis: aioredis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    **kwargs: Any,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(redis, session_factory, **kwargs)
