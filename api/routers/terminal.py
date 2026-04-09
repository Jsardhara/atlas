"""Master Control Terminal routes."""
import json
import uuid
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/terminal", tags=["terminal"])

VALID_AGENTS = {"commander", "oracle", "guardian", "trader", "sage", "architect"}


class TerminalMessage(BaseModel):
    content: str
    session_id: str | None = None


@router.post("/message")
async def send_message(body: TerminalMessage, request: Request):
    """Route a message to a specific agent using @name prefix, or Commander by default."""
    content = body.content.strip()
    session_id = body.session_id or str(uuid.uuid4())

    # Detect @agent prefix
    target = "commander"
    if content.startswith("@"):
        parts = content.split(" ", 1)
        agent_name = parts[0][1:].lower()
        if agent_name in VALID_AGENTS:
            target = agent_name
            content = parts[1] if len(parts) > 1 else ""

    redis_client: aioredis.Redis = request.app.state.redis
    await redis_client.xadd("atlas:events", {"json": json.dumps({
        "source_agent": "user",
        "target_agent": target,
        "message_type": "chat_message",
        "payload": {"content": content, "session_id": session_id},
        "id": str(uuid.uuid4()),
    })})

    return {"session_id": session_id, "target_agent": target, "status": "sent"}


@router.get("/feed")
async def terminal_feed(request: Request):
    """SSE stream of all agent decisions and status updates."""
    redis_client: aioredis.Redis = request.app.state.redis

    DISPLAY_TYPES = {
        "market_signal", "trade_approved", "trade_rejected", "order_placed",
        "order_filled", "position_opened", "position_closed", "learning_insight",
        "strategy_proposed", "backtest_complete", "agent_status", "alert_created",
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
