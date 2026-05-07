"""System health + alerts router.

``/system/health`` returns HTTP 503 when Postgres or Redis is unreachable,
or when any registered agent's ``last_heartbeat`` is older than 60 s.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..dependencies import get_db

router = APIRouter(prefix="/system", tags=["system"])

HEARTBEAT_STALE_SEC = 60


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _agent_is_stale(last_heartbeat: datetime | None) -> bool:
    if last_heartbeat is None:
        return True
    if last_heartbeat.tzinfo is None:
        last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
    return last_heartbeat < _now_utc() - timedelta(seconds=HEARTBEAT_STALE_SEC)


@router.get("/health")
async def health(request: Request):
    """Aggregate health probe.

    Returns 200 when DB + Redis healthy and every agent has a fresh heartbeat
    in ``running`` state. Returns 503 with the same body shape otherwise.
    """
    status: dict = {
        "postgres": "ok",
        "redis": "ok",
        "agents": {},
        "stale_agents": [],
    }

    db_ok = True
    try:
        async with get_db(request) as sess:
            await sess.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        status["postgres"] = f"error: {exc}"

    redis_ok = True
    try:
        redis = request.app.state.redis
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        redis_ok = False
        status["redis"] = f"error: {exc}"

    agents_ok = True
    if db_ok:
        try:
            async with get_db(request) as sess:
                result = await sess.execute(
                    text("SELECT id, state, last_heartbeat FROM agents")
                )
                for row in result.fetchall():
                    agent_state = row.state
                    last_hb = row.last_heartbeat
                    stale = _agent_is_stale(last_hb)
                    status["agents"][row.id] = {
                        "state": agent_state,
                        "last_heartbeat": last_hb.isoformat() if last_hb else None,
                        "stale": stale,
                    }
                    if agent_state != "running" or stale:
                        agents_ok = False
                        status["stale_agents"].append(row.id)
        except Exception:
            # Agents table absent shouldn't 503 the whole probe — flag it.
            status["agents"] = {}

    overall_ok = db_ok and redis_ok and agents_ok
    status["status"] = "healthy" if overall_ok else "degraded"
    code = 200 if overall_ok else 503
    return JSONResponse(content=status, status_code=code)


@router.get("/alerts")
async def get_alerts(request: Request, status: str = "pending"):
    async with get_db(request) as sess:
        result = await sess.execute(
            text(
                """
                SELECT id, severity, title, message, auto_action,
                       countdown_secs, status, created_at
                FROM alerts WHERE status = :status
                ORDER BY created_at DESC LIMIT 20
                """
            ),
            {"status": status},
        )
        return [dict(r._mapping) for r in result.fetchall()]


@router.get("/paper-readiness")
async def paper_readiness(request: Request):
    async with get_db(request) as sess:
        result = await sess.execute(
            text("SELECT * FROM paper_trading_stats ORDER BY updated_at DESC LIMIT 1")
        )
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
