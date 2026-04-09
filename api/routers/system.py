from fastapi import APIRouter, Request
from sqlalchemy import text
from ..dependencies import get_db

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health(request: Request):
    status = {"postgres": "ok", "redis": "ok", "agents": {}}
    try:
        async with get_db(request) as sess:
            await sess.execute(text("SELECT 1"))
    except Exception as e:
        status["postgres"] = f"error: {e}"

    try:
        redis = request.app.state.redis
        await redis.ping()
    except Exception as e:
        status["redis"] = f"error: {e}"

    try:
        async with get_db(request) as sess:
            result = await sess.execute(text(
                "SELECT id, state, last_heartbeat FROM agents"
            ))
            for row in result.fetchall():
                status["agents"][row.id] = {
                    "state": row.state,
                    "last_heartbeat": row.last_heartbeat.isoformat() if row.last_heartbeat else None,
                }
    except Exception:
        pass

    overall = "healthy" if status["postgres"] == "ok" and status["redis"] == "ok" else "degraded"
    return {"status": overall, **status}


@router.get("/alerts")
async def get_alerts(request: Request, status: str = "pending"):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT id, severity, title, message, auto_action,
                   countdown_secs, status, created_at
            FROM alerts WHERE status = :status
            ORDER BY created_at DESC LIMIT 20
        """), {"status": status})
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/paper-readiness")
async def paper_readiness(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(text(
            "SELECT * FROM paper_trading_stats ORDER BY updated_at DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            return {}
        data = dict(row._mapping)
        data["thresholds"] = {
            "trades_target": 30,
            "days_target": 14,
            "win_rate_target": 0.52,
            "pnl_target": 0.08,
            "drawdown_limit": 0.15,
        }
        return data
