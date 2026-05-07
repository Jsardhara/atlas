"""Master Control Terminal routes.

Default chat target was Commander prior to Phase 2; Commander is now removed
and the orchestrator role is owned by Jarvis on the host. Unprefixed messages
are forwarded to Jarvis at ``http://localhost:8765/api/jarvis/terminal``.
"""
import json
import logging
import os
import uuid
from typing import AsyncIterator

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terminal", tags=["terminal"])

VALID_AGENTS = {"oracle", "guardian", "trader", "sage", "architect"}

JARVIS_CHAT_URL = os.environ.get(
    "JARVIS_CHAT_URL", "http://localhost:8765/api/jarvis/terminal"
)
JARVIS_TIMEOUT_SEC = float(os.environ.get("JARVIS_CHAT_TIMEOUT", "10"))


class TerminalMessage(BaseModel):
    content: str
    session_id: str | None = None


async def _forward_to_jarvis(content: str, session_id: str) -> dict:
    """POST the content to Jarvis chat. Caller handles failure modes."""
    async with httpx.AsyncClient(timeout=JARVIS_TIMEOUT_SEC) as client:
        resp = await client.post(
            JARVIS_CHAT_URL,
            json={"message": content, "session_id": session_id},
        )
        resp.raise_for_status()
        return resp.json()


@router.post("/message")
async def send_message(body: TerminalMessage, request: Request):
    """Route a message via @agent prefix, or forward to Jarvis by default."""
    content = body.content.strip()
    session_id = body.session_id or str(uuid.uuid4())

    # Detect @agent prefix (one of the locked five)
    if content.startswith("@"):
        parts = content.split(" ", 1)
        agent_name = parts[0][1:].lower()
        if agent_name in VALID_AGENTS:
            target = agent_name
            content = parts[1] if len(parts) > 1 else ""
            redis_client: aioredis.Redis = request.app.state.redis
            await redis_client.xadd(
                "atlas:events",
                {
                    "json": json.dumps(
                        {
                            "source_agent": "user",
                            "target_agent": target,
                            "message_type": "chat_message",
                            "payload": {
                                "content": content,
                                "session_id": session_id,
                            },
                            "id": str(uuid.uuid4()),
                        }
                    )
                },
            )
            return {
                "session_id": session_id,
                "target_agent": target,
                "status": "sent",
            }

    # No @-prefix — forward to Jarvis as the top-level orchestrator.
    try:
        result = await _forward_to_jarvis(content, session_id)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
        logger.warning("Jarvis chat unreachable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "jarvis_unreachable: Atlas terminal needs Jarvis at "
                f"{JARVIS_CHAT_URL}. Start the Jarvis API or use "
                "@oracle/@architect/@guardian/@trader/@sage prefix."
            ),
        ) from exc

    return {
        "session_id": session_id,
        "target_agent": "jarvis",
        "status": "forwarded",
        "result": result,
    }


@router.get("/feed")
async def terminal_feed(request: Request):
    """SSE stream of all agent decisions and status updates."""
    redis_client: aioredis.Redis = request.app.state.redis

    DISPLAY_TYPES = {
        "market_signal", "trade_approved", "trade_rejected", "order_placed",
        "order_filled", "position_opened", "position_closed", "learning_insight",
        "strategy_proposed", "backtest_complete", "agent_status",
        "chat_response", "pipeline_decision", "performance_report",
    }

    async def stream() -> AsyncIterator[str]:
        last_id = "$"
        while True:
            results = await redis_client.xread({"atlas:events": last_id}, count=20, block=1000)
            if results:
                for _, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            data = json.loads(fields.get("json", "{}"))
                            if data.get("message_type") in DISPLAY_TYPES:
                                yield f"data: {json.dumps(data)}\n\n"
                        except Exception:
                            pass

    return StreamingResponse(stream(), media_type="text/event-stream")
