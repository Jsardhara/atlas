"""Trade management routes."""
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from ..dependencies import get_db

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("")
async def list_trades(
    request: Request,
    status: str | None = None,
    pair: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if status:
        filters.append("status = :status")
        params["status"] = status
    if pair:
        filters.append("pair = :pair")
        params["pair"] = pair
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    async with get_db(request) as sess:
        result = await sess.execute(text(f"""
            SELECT id, signal_id, pair, side, order_type, leverage,
                   requested_size, filled_size, entry_price, exit_price,
                   stop_loss, take_profit, status, pnl_usd, pnl_pct,
                   fees_usd, opened_at, closed_at, close_reason, is_paper,
                   guardian_approved, agent_notes
            FROM trades {where}
            ORDER BY opened_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """), params)
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/open")
async def get_open_trades(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT id, pair, side, leverage, entry_price, stop_loss,
                   take_profit, opened_at, pnl_usd, pnl_pct, is_paper
            FROM trades WHERE status = 'open'
            ORDER BY opened_at DESC
        """))
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/stats")
async def trade_stats(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                COUNT(*) FILTER (WHERE pnl_usd <= 0) as losses,
                ROUND(AVG(pnl_usd)::numeric, 2) as avg_pnl_usd,
                ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl_usd,
                MAX(pnl_usd) as best_trade_usd,
                MIN(pnl_usd) as worst_trade_usd,
                ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl_pct
            FROM trades WHERE status = 'closed'
        """))
        row = dict(result.fetchone()._mapping)
        total = row["total"] or 1
        row["win_rate"] = round((row["wins"] or 0) / total, 4)
        return row


@router.get("/{trade_id}")
async def get_trade(trade_id: str, request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT * FROM trades WHERE id = :id"
        ), {"id": trade_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(404, "Trade not found")
        return dict(row._mapping)


@router.post("/{trade_id}/close")
async def manual_close_trade(trade_id: str, request: Request):
    """Signal Trader agent to close this position immediately."""
    import redis.asyncio as aioredis
    redis_client: aioredis.Redis = request.app.state.redis
    await redis_client.xadd("atlas:events", {"json": json.dumps({
        "source_agent": "user",
        "target_agent": "trader",
        "message_type": "user_command",
        "payload": {"command": "close_trade", "trade_id": trade_id},
        "id": str(uuid.uuid4()),
        "priority": "5",
    })})
    return {"trade_id": trade_id, "status": "close_requested"}
