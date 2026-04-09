import json
import uuid
from fastapi import APIRouter, Request
from sqlalchemy import text
from ..dependencies import get_db

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(request: Request, limit: int = 50):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT id, pair, direction, confidence, reasoning,
                   entry_price, stop_loss, take_profit, status,
                   guardian_notes, created_at
            FROM signals ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit})
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/active")
async def active_signals(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT id, pair, direction, confidence, entry_price,
                   stop_loss, take_profit, status, created_at
            FROM signals WHERE status IN ('pending', 'approved')
            ORDER BY created_at DESC
        """))
        return [dict(r._mapping) for r in result.fetchall()]


@router.post("/{signal_id}/override")
async def override_signal(signal_id: str, action: str, request: Request):
    """User manually approve or reject a pending signal."""
    import redis.asyncio as aioredis
    redis_client: aioredis.Redis = request.app.state.redis

    async with get_db(request) as sess:
        new_status = "approved" if action == "approve" else "rejected"
        await sess.execute(text(
            "UPDATE signals SET status = :status WHERE id = :id"
        ), {"status": new_status, "id": signal_id})
        await sess.commit()

    if action == "approve":
        await redis_client.xadd("atlas:events", {"json": json.dumps({
            "source_agent": "user",
            "target_agent": "trader",
            "message_type": "trade_approved",
            "payload": {"signal_id": signal_id, "override": True},
            "id": str(uuid.uuid4()),
        })})

    return {"signal_id": signal_id, "action": action}
