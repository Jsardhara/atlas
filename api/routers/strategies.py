import json
import uuid
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from ..dependencies import get_db

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
async def list_strategies(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT id, name, version, status, author, performance_metrics,
                   created_at, activated_at
            FROM strategies ORDER BY created_at DESC
        """))
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT * FROM strategies WHERE id = :id"
        ), {"id": strategy_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(404, "Strategy not found")

        backtests = await sess.execute(text("""
            SELECT id, timerange, status, sharpe_ratio, max_drawdown,
                   total_return, win_rate, started_at, completed_at
            FROM backtests WHERE strategy_id = :id ORDER BY started_at DESC
        """), {"id": strategy_id})

        return {**dict(row._mapping),
                "backtests": [dict(b._mapping) for b in backtests.fetchall()]}


@router.post("/{strategy_id}/activate")
async def activate_strategy(strategy_id: str, request: Request):
    async with get_db(request) as sess:
        await sess.execute(text("""
            UPDATE strategies
            SET status = 'active', activated_at = now()
            WHERE id = :id
        """), {"id": strategy_id})
        await sess.commit()
    return {"strategy_id": strategy_id, "status": "active"}


@router.post("/{strategy_id}/archive")
async def archive_strategy(strategy_id: str, request: Request):
    async with get_db(request) as sess:
        await sess.execute(text(
            "UPDATE strategies SET status = 'archived' WHERE id = :id"
        ), {"id": strategy_id})
        await sess.commit()
    return {"strategy_id": strategy_id, "status": "archived"}


@router.post("/generate")
async def generate_strategy(request: Request):
    """Tell Architect to generate a new strategy."""
    import redis.asyncio as aioredis
    redis_client: aioredis.Redis = request.app.state.redis
    await redis_client.xadd("atlas:events", {"json": json.dumps({
        "source_agent": "user",
        "target_agent": "architect",
        "message_type": "user_command",
        "payload": {"command": "generate_strategy"},
        "id": str(uuid.uuid4()),
    })})
    return {"status": "requested"}
