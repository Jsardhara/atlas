"""WebSocket endpoint — streams Atlas bus events to subscribed clients.

Optional ``?type=`` query parameter filters the firehose to a comma-separated
list of message types. When omitted, all events are forwarded.

Example::

    ws://localhost:8000/ws?type=pipeline_decision,trade_approved
"""
import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_KEY = "atlas:events"


def _parse_type_filter(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    type: str | None = Query(default=None),  # noqa: A002 — FastAPI param name
):
    """Stream events. Optional ``type`` filter is a comma-separated allowlist."""
    await manager.connect(websocket)
    redis_client = None
    type_filter = _parse_type_filter(type)
    try:
        redis_url = websocket.app.state.redis_url
        redis_client = aioredis.from_url(redis_url, decode_responses=True)

        # Stream from Redis to this client
        last_id = "$"
        while True:
            results = await redis_client.xread(
                {STREAM_KEY: last_id}, count=20, block=500
            )
            if results:
                for _, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            payload = json.loads(fields.get("json", "{}"))
                            if (
                                type_filter
                                and payload.get("message_type") not in type_filter
                            ):
                                continue
                            await websocket.send_json(payload)
                        except Exception:
                            pass
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WS error: %s", e)
    finally:
        manager.disconnect(websocket)
        if redis_client:
            await redis_client.aclose()
