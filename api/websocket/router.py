"""WebSocket endpoint — streams all Atlas bus events to authenticated clients."""
import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

STREAM_KEY = "atlas:events"


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    redis_client = None
    try:
        redis_url = websocket.app.state.redis_url
        redis_client = aioredis.from_url(redis_url, decode_responses=True)

        # Stream from Redis to this client
        last_id = "$"
        while True:
            results = await redis_client.xread({STREAM_KEY: last_id}, count=20, block=500)
            if results:
                for _, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        try:
                            payload = json.loads(fields.get("json", "{}"))
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
