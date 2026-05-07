"""Agent control, status, and individual chat routes."""
import json
import uuid
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..dependencies import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class ChatRequest(BaseModel):
    content: str
    session_id: str | None = None


class ConfigPatch(BaseModel):
    config: dict


@router.get("")
async def list_agents(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT id, display_name, model, state, config, last_heartbeat FROM agents ORDER BY id"
        ))
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT id, display_name, model, personality, state, config, last_heartbeat "
            "FROM agents WHERE id = :id"
        ), {"id": agent_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(404, f"Agent {agent_id} not found")

        # Recent activity from events
        events = await sess.execute(text(
            "SELECT event_type, payload, occurred_at FROM events "
            "WHERE source = :id ORDER BY occurred_at DESC LIMIT 20"
        ), {"id": agent_id})
        return {
            **dict(row._mapping),
            "recent_activity": [dict(e._mapping) for e in events.fetchall()],
        }


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str, request: Request):
    return await _send_command(agent_id, "pause", request)


@router.post("/{agent_id}/resume")
async def resume_agent(agent_id: str, request: Request):
    return await _send_command(agent_id, "resume", request)


@router.patch("/{agent_id}/config")
async def update_config(agent_id: str, body: ConfigPatch, request: Request):
    async with get_db(request) as sess:
        await sess.execute(text(
            "UPDATE agents SET config = config || CAST(:cfg AS jsonb) WHERE id = :id"
        ), {"id": agent_id, "cfg": json.dumps(body.config)})
        await sess.commit()
    return {"status": "updated"}


@router.post("/{agent_id}/chat")
async def chat_with_agent(agent_id: str, body: ChatRequest, request: Request):
    session_id = body.session_id or str(uuid.uuid4())
    redis: aioredis.Redis = request.app.state.redis

    # Persist user message
    async with get_db(request) as sess:
        await sess.execute(text("""
            INSERT INTO chat_messages (session_id, role, agent_id, content)
            VALUES (:sid::uuid, 'user', :agent, :content)
        """), {"sid": session_id, "agent": agent_id, "content": body.content})
        await sess.commit()

    # Publish chat message to bus — agent will respond
    await redis.xadd("atlas:events", {"json": json.dumps({
        "source_agent": "user",
        "target_agent": agent_id,
        "message_type": "chat_message",
        "payload": {"content": body.content, "session_id": session_id},
        "id": str(uuid.uuid4()),
    })})

    return {"session_id": session_id, "status": "sent"}


@router.get("/{agent_id}/chat/stream")
async def stream_chat(agent_id: str, session_id: str, request: Request):
    """SSE stream of chat responses for a session."""
    redis: aioredis.Redis = request.app.state.redis

    async def event_stream() -> AsyncIterator[str]:
        last_id = "$"
        timeout = 30  # seconds
        elapsed = 0
        while elapsed < timeout:
            results = await redis.xread({"atlas:events": last_id}, count=10, block=500)
            if results:
                for _, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            data = json.loads(fields.get("json", "{}"))
                            if (data.get("message_type") == "chat_response"
                                    and data.get("source_agent") == agent_id
                                    and data.get("payload", {}).get("session_id") == session_id):
                                content = data["payload"].get("content", "")
                                yield f"data: {json.dumps({'content': content})}\n\n"
                                return
                        except Exception:
                            pass
            elapsed += 0.5

        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{agent_id}/memory")
async def get_memory(agent_id: str, request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT memory_key, value, updated_at FROM agent_memory WHERE agent_id = :id"
        ), {"id": agent_id})
        return {r.memory_key: {"value": r.value, "updated_at": r.updated_at}
                for r in result.fetchall()}


async def _send_command(agent_id: str, command: str, request: Request):
    redis: aioredis.Redis = request.app.state.redis
    await redis.xadd("atlas:events", {"json": json.dumps({
        "source_agent": "user",
        "target_agent": agent_id,
        "message_type": "agent_command",
        "payload": {"command": command},
        "id": str(uuid.uuid4()),
        "priority": "5",
    })})
    # Also update DB state immediately
    async with get_db(request) as sess:
        new_state = "paused" if command == "pause" else "running"
        await sess.execute(text(
            "UPDATE agents SET state = :state WHERE id = :id"
        ), {"state": new_state, "id": agent_id})
        await sess.commit()
    return {"agent_id": agent_id, "command": command, "status": "sent"}
