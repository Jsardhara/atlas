from fastapi import APIRouter, Request
from sqlalchemy import text
from ..dependencies import get_db

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
async def current_portfolio(request: Request):
    async with get_db(request) as sess:
        snap = await sess.execute(text("""
            SELECT total_usd, available_usd, open_positions,
                   realized_pnl, unrealized_pnl, snapshot_at, is_paper
            FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1
        """))
        row = snap.fetchone()
        return dict(row._mapping) if row else {}


@router.get("/history")
async def portfolio_history(request: Request, limit: int = 200):
    async with get_db(request) as sess:
        result = await sess.execute(text("""
            SELECT snapshot_at, total_usd, realized_pnl, unrealized_pnl
            FROM portfolio_snapshots
            ORDER BY snapshot_at DESC LIMIT :limit
        """), {"limit": limit})
        rows = [dict(r._mapping) for r in result.fetchall()]
        return list(reversed(rows))  # chronological order for charts
