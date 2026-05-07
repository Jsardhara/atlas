"""Daily LLM cost rollup — schema-compatible with Jarvis ``useDailyCost``.

Reads from the ``llm_calls`` table populated by
``agents/shared/claude_client.py`` and returns per-agent and per-model
token + USD totals for one calendar date (UTC).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from ..dependencies import get_db
from ..middleware.bearer_auth import verify_bearer_token

router = APIRouter(
    prefix="/api/cost",
    tags=["cost"],
    dependencies=[Depends(verify_bearer_token)],
)


def _parse_date(date_str: str | None) -> date:
    if not date_str:
        return datetime.now(tz=timezone.utc).date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid date_str (expected YYYY-MM-DD): {exc}",
        ) from exc


def _empty_rollup(target_date: date) -> dict[str, Any]:
    return {
        "date": target_date.isoformat(),
        "total_usd": 0.0,
        "by_agent": {},
        "by_model": {},
        "call_count": 0,
    }


@router.get("/rollup")
async def cost_rollup(
    request: Request,
    date_str: str | None = Query(default=None),
) -> dict[str, Any]:
    """Aggregate ``llm_calls`` rows for the given UTC date.

    Response shape matches Jarvis ``useDailyCost`` consumer (see
    ``web/src/hooks/useDailyCost.ts``):

    ``{date, total_usd, by_agent: {agent: {calls, input_tokens, output_tokens, cost_usd}},
        by_model: {...}, call_count}``
    """
    target_date = _parse_date(date_str)
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    try:
        async with get_db(request) as sess:
            result = await sess.execute(
                text(
                    """
                    SELECT agent_id, model,
                           COUNT(*) AS calls,
                           COALESCE(SUM(input_tokens), 0) AS in_tok,
                           COALESCE(SUM(output_tokens), 0) AS out_tok,
                           COALESCE(SUM(cost_usd_estimate), 0) AS cost
                    FROM llm_calls
                    WHERE ts >= :start AND ts < :end
                    GROUP BY agent_id, model
                    """
                ),
                {"start": day_start, "end": day_end},
            )
            rows = result.fetchall()
    except Exception:
        # Fresh DB or table missing → return zeroed envelope rather than 500.
        return _empty_rollup(target_date)

    by_agent: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    total_usd = 0.0
    call_count = 0

    for row in rows:
        agent_id = str(row.agent_id)
        model = str(row.model)
        calls = int(row.calls or 0)
        in_tok = int(row.in_tok or 0)
        out_tok = int(row.out_tok or 0)
        cost = float(row.cost or 0.0)

        agent_bucket = by_agent.setdefault(
            agent_id,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        )
        agent_bucket["calls"] += calls
        agent_bucket["input_tokens"] += in_tok
        agent_bucket["output_tokens"] += out_tok
        agent_bucket["cost_usd"] += cost

        model_bucket = by_model.setdefault(
            model,
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        )
        model_bucket["calls"] += calls
        model_bucket["input_tokens"] += in_tok
        model_bucket["output_tokens"] += out_tok
        model_bucket["cost_usd"] += cost

        total_usd += cost
        call_count += calls

    return {
        "date": target_date.isoformat(),
        "total_usd": round(total_usd, 6),
        "by_agent": by_agent,
        "by_model": by_model,
        "call_count": call_count,
    }


__all__ = ["router"]
