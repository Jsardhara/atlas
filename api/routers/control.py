"""Control surface — Jarvis decision-layer entrypoints.

Bearer-protected routes that let Jarvis (or any external orchestrator) drive
ATLAS without going through the dashboard:

* ``POST /control/pause-agent`` / ``POST /control/resume-agent`` — toggle
  the ``state`` column of an agent (``running`` / ``paused``). The pipeline
  orchestrator's ``_decide`` already gates on this column, so a paused
  agent stops receiving new work immediately.
* ``POST /control/strategy-weights`` / ``GET /control/strategy-weights`` —
  Architect-rank multipliers, stored as JSON in the Redis key
  ``atlas:strategy_weights``. Each Architect rank pass multiplies the raw
  score by the named weight (default 1.0) before sorting.
* ``POST /control/oracle-scan`` — fire an ad-hoc Oracle scan outside the
  built-in 15-minute cycle. Useful when Jarvis observes a volatility spike.

Routes never touch agent code directly — they publish ``USER_COMMAND``
messages on the Redis stream, the same pattern the existing pipeline
endpoints use.
"""

from __future__ import annotations

import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..dependencies import get_db
from ..middleware.bearer_auth import verify_bearer_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/control",
    tags=["control"],
    dependencies=[Depends(verify_bearer_token)],
)

STREAM_KEY = "atlas:events"
STRATEGY_WEIGHTS_KEY = "atlas:strategy_weights"
VALID_AGENT_IDS = {"oracle", "architect", "guardian", "trader", "sage"}


# ── request shapes ───────────────────────────────────────────────────────


class AgentControlRequest(BaseModel):
    agent_id: str = Field(..., description="One of oracle|architect|guardian|trader|sage")


class StrategyWeightsRequest(BaseModel):
    weights: dict[str, float] = Field(
        ...,
        description="Map of strategy name -> weight multiplier. Empty dict clears all.",
    )


class OracleScanRequest(BaseModel):
    universe: list[str] | None = None
    reason: str | None = Field(default=None, description="Why Jarvis is firing this scan")


# ── helpers ──────────────────────────────────────────────────────────────


def _validate_agent_id(agent_id: str) -> str:
    aid = agent_id.strip().lower()
    if aid not in VALID_AGENT_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown_agent_id: {agent_id} (expected one of {sorted(VALID_AGENT_IDS)})",
        )
    return aid


async def _publish_command(
    redis: aioredis.Redis, target_agent: str, command: str, payload: dict | None = None
) -> str:
    msg_id = str(uuid.uuid4())
    body = {
        "source_agent": "jarvis",
        "target_agent": target_agent,
        "message_type": "agent_command",
        "payload": {"command": command, **(payload or {})},
        "id": msg_id,
        "priority": "5",
    }
    await redis.xadd(STREAM_KEY, {"json": json.dumps(body)})
    return msg_id


# ── routes ───────────────────────────────────────────────────────────────


@router.post("/pause-agent")
async def pause_agent(body: AgentControlRequest, request: Request) -> dict:
    aid = _validate_agent_id(body.agent_id)
    redis: aioredis.Redis = request.app.state.redis
    msg_id = await _publish_command(redis, aid, "pause")
    async with get_db(request) as sess:
        await sess.execute(
            text("UPDATE agents SET state = 'paused' WHERE id = :id"),
            {"id": aid},
        )
        await sess.commit()
    logger.info("control.pause_agent agent_id=%s msg_id=%s", aid, msg_id)
    return {"agent_id": aid, "state": "paused", "command_id": msg_id}


@router.post("/resume-agent")
async def resume_agent(body: AgentControlRequest, request: Request) -> dict:
    aid = _validate_agent_id(body.agent_id)
    redis: aioredis.Redis = request.app.state.redis
    msg_id = await _publish_command(redis, aid, "resume")
    async with get_db(request) as sess:
        await sess.execute(
            text("UPDATE agents SET state = 'running' WHERE id = :id"),
            {"id": aid},
        )
        await sess.commit()
    logger.info("control.resume_agent agent_id=%s msg_id=%s", aid, msg_id)
    return {"agent_id": aid, "state": "running", "command_id": msg_id}


@router.get("/agent-state")
async def list_agent_state(request: Request) -> dict:
    async with get_db(request) as sess:
        rows = await sess.execute(
            text("SELECT id, state, last_heartbeat FROM agents ORDER BY id")
        )
        return {
            "agents": [
                {
                    "id": r.id,
                    "state": r.state,
                    "last_heartbeat": r.last_heartbeat.isoformat()
                    if r.last_heartbeat
                    else None,
                }
                for r in rows.fetchall()
            ]
        }


@router.post("/strategy-weights")
async def set_strategy_weights(
    body: StrategyWeightsRequest, request: Request
) -> dict:
    redis: aioredis.Redis = request.app.state.redis
    cleaned = {k.strip(): float(v) for k, v in body.weights.items() if k.strip()}
    if cleaned:
        await redis.set(STRATEGY_WEIGHTS_KEY, json.dumps(cleaned))
    else:
        await redis.delete(STRATEGY_WEIGHTS_KEY)
    logger.info("control.strategy_weights count=%d", len(cleaned))
    return {"weights": cleaned, "count": len(cleaned)}


@router.get("/strategy-weights")
async def get_strategy_weights(request: Request) -> dict:
    redis: aioredis.Redis = request.app.state.redis
    raw = await redis.get(STRATEGY_WEIGHTS_KEY)
    if not raw:
        return {"weights": {}, "count": 0}
    try:
        weights = json.loads(raw)
    except (ValueError, TypeError):
        weights = {}
    return {"weights": weights, "count": len(weights)}


@router.post("/oracle-scan")
async def trigger_oracle_scan(
    body: OracleScanRequest, request: Request
) -> dict:
    redis: aioredis.Redis = request.app.state.redis
    msg_id = await _publish_command(
        redis,
        "oracle",
        "scan",
        {"universe": body.universe, "reason": body.reason or "jarvis-triggered"},
    )
    logger.info("control.oracle_scan reason=%s msg_id=%s", body.reason, msg_id)
    return {"command_id": msg_id, "reason": body.reason or "jarvis-triggered"}


__all__ = ["router", "STRATEGY_WEIGHTS_KEY"]
