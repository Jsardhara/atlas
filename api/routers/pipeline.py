"""Explicit pipeline REST endpoints — Jarvis bridge entrypoints.

Each route publishes a ``USER_COMMAND`` (or synthetic trigger) onto the
Redis ``atlas:events`` stream and waits for the correlated reply event
from the relevant agent. All routes:

* require ``Authorization: Bearer <token>`` (when configured);
* accept an optional ``X-Idempotency-Key`` header for 60 s dedup;
* return a uniform envelope: ``{status, correlation_id, result}``;
* fall back to status ``"timeout"`` with ``HTTP 202`` and a ``job_id``
  when no reply arrives within the configured timeout.

Routes never touch agent code directly — agents respond by publishing
their own events on the same stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Iterable

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..middleware.bearer_auth import verify_bearer_token
from ..middleware.idempotency import (
    IdempotencyDecision,
    idempotency_check,
    store_idempotent_response,
)

# Avoid hard import of shared.protocols at top level so the router stays
# importable in environments where the agents/ tree is not on sys.path
# (rare, but TestClient setups vary).
from shared.protocols import (  # type: ignore[import-not-found]
    AgentID,
    AtlasMessage,
    MessageType,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(verify_bearer_token)],
)

STREAM_KEY = "atlas:events"
DEFAULT_TIMEOUT_SEC = 60.0


# ── request/response shapes ──────────────────────────────────────────────


class OracleScanRequest(BaseModel):
    universe: list[str] | None = None
    top_n: int | None = None


class ArchitectRankRequest(BaseModel):
    candidates: list[dict[str, Any]] | None = None


class GuardianCheckRequest(BaseModel):
    signal_id: str


class TraderExecuteRequest(BaseModel):
    signal_id: str
    mode: str = Field(default="paper", pattern="^(paper|live)$")


class SageReviewRequest(BaseModel):
    trade_id: str


# ── helpers ──────────────────────────────────────────────────────────────


def _envelope(
    status: str,
    correlation_id: str,
    result: Any | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "status": status,
        "correlation_id": correlation_id,
        "result": result if result is not None else {},
    }
    if job_id:
        body["job_id"] = job_id
    return body


async def _publish(redis: aioredis.Redis, msg: AtlasMessage) -> None:
    await redis.xadd(STREAM_KEY, {"json": msg.model_dump_json()})


async def _wait_for_correlated(
    redis: aioredis.Redis,
    correlation_id: str,
    accept_types: Iterable[str],
    timeout_sec: float,
) -> dict[str, Any] | None:
    """Subscribe to the stream tail and return the first matching event."""
    accept_set = set(accept_types)
    last_id = "$"
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        block_ms = max(50, min(int(remaining * 1000), 2000))
        try:
            res = await redis.xread(
                {STREAM_KEY: last_id}, count=20, block=block_ms
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("xread failed in pipeline wait: %s", exc)
            return None
        if not res:
            continue
        for _stream, messages in res:
            for msg_id, fields in messages:
                last_id = msg_id
                try:
                    data = json.loads(fields.get("json", "{}"))
                except (ValueError, TypeError):
                    continue
                if data.get("correlation_id") != correlation_id:
                    continue
                if data.get("message_type") not in accept_set:
                    continue
                return data
    # unreachable
    return None


async def _run_pipeline_step(
    request: Request,
    decision: IdempotencyDecision,
    *,
    target_agent: AgentID,
    message_type: MessageType,
    accept_replies: Iterable[MessageType],
    payload: dict[str, Any],
    timeout_sec: float | None = None,
) -> JSONResponse:
    """Shared logic for all pipeline endpoints."""
    if decision.is_hit:
        return JSONResponse(
            content=decision.cached_body,
            status_code=decision.cached_status or 200,
        )

    # Resolve the module-level default at call time so tests can monkeypatch
    # ``DEFAULT_TIMEOUT_SEC`` without rewiring every endpoint signature.
    effective_timeout = (
        timeout_sec if timeout_sec is not None else DEFAULT_TIMEOUT_SEC
    )

    redis: aioredis.Redis = request.app.state.redis
    correlation_id = payload.get("signal_id") or payload.get("trade_id") or str(uuid.uuid4())

    msg = AtlasMessage(
        source_agent=AgentID.SYSTEM,
        target_agent=target_agent,
        message_type=message_type,
        correlation_id=correlation_id,
        payload=payload,
    )
    await _publish(redis, msg)

    accept_values = [t.value for t in accept_replies]
    reply = await _wait_for_correlated(
        redis, correlation_id, accept_values, effective_timeout
    )

    if reply is None:
        body = _envelope(
            status="timeout",
            correlation_id=correlation_id,
            job_id=correlation_id,
        )
        await store_idempotent_response(request, decision, body, status_code=202)
        return JSONResponse(content=body, status_code=202)

    body = _envelope(
        status="ok",
        correlation_id=correlation_id,
        result={
            "message_type": reply.get("message_type"),
            "payload": reply.get("payload", {}),
        },
    )
    await store_idempotent_response(request, decision, body, status_code=200)
    return JSONResponse(content=body, status_code=200)


# ── endpoints ────────────────────────────────────────────────────────────


@router.post("/oracle-scan")
async def oracle_scan(
    body: OracleScanRequest,
    request: Request,
    decision: IdempotencyDecision = Depends(idempotency_check),
) -> JSONResponse:
    return await _run_pipeline_step(
        request,
        decision,
        target_agent=AgentID.ORACLE,
        message_type=MessageType.USER_COMMAND,
        accept_replies=[MessageType.RESEARCH_UPDATE, MessageType.MARKET_SIGNAL],
        payload={
            "command": "scan",
            "universe": body.universe or [],
            "top_n": body.top_n,
        },
    )


@router.post("/architect-rank")
async def architect_rank(
    body: ArchitectRankRequest,
    request: Request,
    decision: IdempotencyDecision = Depends(idempotency_check),
) -> JSONResponse:
    return await _run_pipeline_step(
        request,
        decision,
        target_agent=AgentID.ARCHITECT,
        message_type=MessageType.USER_COMMAND,
        accept_replies=[MessageType.STRATEGY_PROPOSED],
        payload={
            "command": "rank",
            "candidates": body.candidates or [],
        },
    )


@router.post("/guardian-check")
async def guardian_check(
    body: GuardianCheckRequest,
    request: Request,
    decision: IdempotencyDecision = Depends(idempotency_check),
) -> JSONResponse:
    return await _run_pipeline_step(
        request,
        decision,
        target_agent=AgentID.GUARDIAN,
        message_type=MessageType.USER_COMMAND,
        accept_replies=[
            MessageType.TRADE_APPROVED,
            MessageType.TRADE_REJECTED,
            MessageType.TRADE_MODIFIED,
        ],
        payload={"command": "check", "signal_id": body.signal_id},
    )


@router.post("/trader-execute")
async def trader_execute(
    body: TraderExecuteRequest,
    request: Request,
    decision: IdempotencyDecision = Depends(idempotency_check),
) -> JSONResponse:
    return await _run_pipeline_step(
        request,
        decision,
        target_agent=AgentID.TRADER,
        message_type=MessageType.TRADE_APPROVED,
        accept_replies=[
            MessageType.ORDER_PLACED,
            MessageType.POSITION_OPENED,
            MessageType.ORDER_FILLED,
        ],
        payload={"signal_id": body.signal_id, "mode": body.mode},
    )


@router.post("/sage-review")
async def sage_review(
    body: SageReviewRequest,
    request: Request,
    decision: IdempotencyDecision = Depends(idempotency_check),
) -> JSONResponse:
    return await _run_pipeline_step(
        request,
        decision,
        target_agent=AgentID.SAGE,
        message_type=MessageType.USER_COMMAND,
        accept_replies=[MessageType.LEARNING_INSIGHT],
        payload={"command": "review", "trade_id": body.trade_id},
    )


__all__ = ["router"]
