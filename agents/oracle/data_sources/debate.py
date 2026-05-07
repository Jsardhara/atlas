"""Native bull/bear/judge debate via Claude Agent SDK.

Replaces the Tauric (TradingAgents) integration with a self-contained
debate that runs on the operator's Claude Code subscription. Three
sequential ``ClaudeClient.chat`` calls per ticker:

  bull_analyst   (sonnet) -> long thesis + key supporting evidence
  bear_analyst   (sonnet) -> short thesis + counter-evidence
  judge          (opus)   -> winner + decision + rationale

Output dict keys are flat and broker-agnostic so the Oracle prompt
template at ``agents/oracle/agent.py`` consumes them directly. Cached by (ticker, trade_date) in Redis with 24h TTL. Budget
capped via :class:`agents.shared.budget.BudgetTracker` — when the daily
cap is hit the wrapper returns ``None`` instead of raising.

Design notes:

* **One auth path**: ClaudeClient pulls credentials from the host's
  Claude Code session; no API keys live in this module. This is the
  same pattern the five native agents already use.
* **Failure isolation**: every error is caught and logged. Oracle's
  primary screener output is unaffected by debate failures — the wrapper
  returns ``None`` and Oracle proceeds with screener data alone.
* **Budget vs. cap**: the daily cap is in USD because the older Tauric
  module set the precedent. Under the Claude Code subscription the
  per-call dollar cost is informational only — message-quota limits
  are tracked by the SDK separately.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from shared.claude_client import ClaudeClient  # type: ignore[import-not-found]
from shared.config import Settings  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

CACHE_PREFIX = "atlas:debate:cache"
BUDGET_PREFIX = "atlas:budget:debate"
CACHE_TTL_SEC = 60 * 60 * 24  # 24h

BULL_SYSTEM = """You are the bull analyst in an internal investment debate.
Your job is to build the strongest possible long thesis for the given ticker
on the given date. Use the supplied screener bars, news, and any analyst
context provided. Be concrete: cite specific levels, indicators, or news
items. Acknowledge the strongest counter-arguments but explain why the
long case still wins.

Respond with valid JSON only:
{
  "thesis": "<3-6 sentence long case>",
  "key_drivers": ["driver 1", "driver 2", "driver 3"],
  "primary_risk": "<the strongest single risk to the long thesis>",
  "conviction": <float 0-1 — your confidence in this thesis>
}"""

BEAR_SYSTEM = """You are the bear analyst in an internal investment debate.
Your job is to build the strongest possible short or avoid thesis for the
given ticker on the given date. Use the supplied screener bars, news, and
any analyst context. Be concrete: cite specific levels, breakdowns, or
deteriorating fundamentals. Acknowledge the strongest counter-arguments
but explain why the short/avoid case still wins.

Respond with valid JSON only:
{
  "thesis": "<3-6 sentence short/avoid case>",
  "key_drivers": ["driver 1", "driver 2", "driver 3"],
  "primary_risk": "<the strongest single risk to the short thesis>",
  "conviction": <float 0-1 — your confidence in this thesis>
}"""

JUDGE_SYSTEM = """You are the impartial judge in an internal investment debate.
Both sides have presented their cases. Your job is to pick the stronger
argument, decide BUY / SELL / HOLD, and explain why in 2-4 sentences.

A HOLD is appropriate when both sides are weak or evenly matched. Do not
default to HOLD just to avoid a call.

Respond with valid JSON only:
{
  "decision": "BUY" | "SELL" | "HOLD",
  "winner": "bull" | "bear" | "neutral",
  "rationale": "<2-4 sentence explanation>",
  "conviction": <float 0-1 — your confidence in this verdict>
}"""


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _cache_key(symbol: str, trade_date: str) -> str:
    return f"{CACHE_PREFIX}:{symbol.upper()}:{trade_date}"


def _normalize_decision(decision: Any) -> str:
    """Squash arbitrary string output into BUY / SELL / HOLD."""
    if not decision:
        return "HOLD"
    text = str(decision).strip().upper()
    if "BUY" in text or "LONG" in text:
        return "BUY"
    if "SELL" in text or "SHORT" in text:
        return "SELL"
    return "HOLD"


def _normalize_winner(winner: Any) -> str:
    if not winner:
        return "neutral"
    text = str(winner).strip().lower()
    if "bull" in text:
        return "bull"
    if "bear" in text:
        return "bear"
    return "neutral"


def _safe_json(raw: str) -> dict:
    """Parse JSON from a model response. Return ``{}`` on any failure."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("debate JSON parse failed: %s — raw=%r", exc, raw[:200])
        return {}


def _format_market_context(context: dict[str, Any] | None) -> str:
    """Render screener + news context into a compact prompt block."""
    if not context:
        return "(no additional market context)"
    lines: list[str] = []
    snapshot = context.get("snapshot")
    if snapshot:
        lines.append(f"Snapshot: {json.dumps(snapshot)[:400]}")
    score = context.get("score")
    if score is not None:
        lines.append(f"Screener score: {score:+.2f}")
    direction = context.get("suggested_direction")
    if direction:
        lines.append(f"Screener suggested direction: {direction}")
    news_items = context.get("news") or []
    if news_items:
        lines.append("Recent news:")
        for item in news_items[:5]:
            title = item.get("title") if isinstance(item, dict) else str(item)
            lines.append(f"  - {title}")
    fng = context.get("fear_greed")
    if fng:
        lines.append(f"Fear/Greed: {fng}")
    return "\n".join(lines) if lines else "(no additional market context)"


async def _get_cached(redis: Any | None, key: str) -> dict | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("debate cache read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        cached = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("debate cache value not valid JSON: %s", exc)
        return None
    cached["cached"] = True
    return cached


async def _set_cached(redis: Any | None, key: str, payload: dict) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(payload), ex=CACHE_TTL_SEC)
    except Exception as exc:  # noqa: BLE001
        logger.warning("debate cache write failed: %s", exc)


async def _think_json(
    client: ClaudeClient,
    system: str,
    user_prompt: str,
) -> dict:
    """One ClaudeClient.chat call expecting a JSON object response."""
    raw = await client.chat(
        messages=[{"role": "user", "content": user_prompt}],
        system=system,
        temperature=0.2,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return _safe_json(raw)


def _build_user_prompt(symbol: str, trade_date: str, context_block: str) -> str:
    return (
        f"Ticker: {symbol}\n"
        f"Trade date: {trade_date}\n\n"
        f"## Market context\n{context_block}\n\n"
        "Build your thesis and respond in the JSON shape your system prompt specifies."
    )


def _build_judge_prompt(
    symbol: str,
    trade_date: str,
    bull: dict,
    bear: dict,
    context_block: str,
) -> str:
    return (
        f"Ticker: {symbol}\n"
        f"Trade date: {trade_date}\n\n"
        f"## Market context\n{context_block}\n\n"
        f"## Bull case\n{json.dumps(bull, indent=2)}\n\n"
        f"## Bear case\n{json.dumps(bear, indent=2)}\n\n"
        "Pick the stronger argument and respond in the JSON shape your system prompt specifies."
    )


def _make_clients(settings: Settings) -> tuple[ClaudeClient, ClaudeClient]:
    """Two clients: one for analysts (sonnet, fast), one for judge (opus, deep)."""
    analyst_model = settings.debate_analyst_model
    judge_model = settings.debate_judge_model
    return (
        ClaudeClient(model=analyst_model, agent_id="oracle.debate.analyst"),
        ClaudeClient(model=judge_model, agent_id="oracle.debate.judge"),
    )


async def fetch_debate_signal(
    symbol: str,
    trade_date: str | None = None,
    *,
    settings: Settings | None = None,
    redis: Any | None = None,
    budget: Any | None = None,
    market_context: dict[str, Any] | None = None,
) -> dict | None:
    """Run a bull/bear/judge debate for ``symbol`` on ``trade_date``.

    Returns a flat dict on success, or ``None`` when:

    * ``Settings.debate_enabled`` is False
    * the daily budget cap is exhausted
    * any LLM call raises (logged, never re-raised)
    """
    if settings is None:
        from shared.config import get_settings  # type: ignore[import-not-found]

        settings = get_settings()

    if not settings.debate_enabled:
        return None

    date_str = trade_date or _today_utc()
    cache_key = _cache_key(symbol, date_str)

    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        logger.info("[debate] cache hit %s/%s", symbol, date_str)
        return cached

    if budget is not None:
        affordable = await budget.can_afford(
            estimated_cost_usd=settings.debate_per_call_budget_usd,
            daily_cap=settings.debate_daily_budget_usd,
        )
        if not affordable:
            logger.info(
                "[debate] budget exhausted; skipping %s (cap=%.2f)",
                symbol, settings.debate_daily_budget_usd,
            )
            return None

    analyst, judge = _make_clients(settings)
    context_block = _format_market_context(market_context)
    user_prompt = _build_user_prompt(symbol, date_str, context_block)

    try:
        bull, bear = await asyncio.gather(
            _think_json(analyst, BULL_SYSTEM, user_prompt),
            _think_json(analyst, BEAR_SYSTEM, user_prompt),
        )
    except Exception as exc:  # noqa: BLE001 — debate is augment-only
        logger.warning("[debate] analyst phase failed for %s: %s", symbol, exc)
        return None

    judge_prompt = _build_judge_prompt(symbol, date_str, bull, bear, context_block)
    try:
        verdict = await _think_json(judge, JUDGE_SYSTEM, judge_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[debate] judge phase failed for %s: %s", symbol, exc)
        return None

    payload: dict = {
        "symbol": symbol.upper(),
        "trade_date": date_str,
        "decision": _normalize_decision(verdict.get("decision")),
        "rationale": str(verdict.get("rationale", ""))[:2000],
        "conviction": float(verdict.get("conviction") or 0.0),
        "debate_log": {
            "bull": str(bull.get("thesis", ""))[:2000],
            "bear": str(bear.get("thesis", ""))[:2000],
            "winner": _normalize_winner(verdict.get("winner")),
        },
        "analyst_reports": {
            "fundamentals": str(bull.get("key_drivers", "")),
            "sentiment": str(bear.get("key_drivers", "")),
            "news": str(market_context.get("news", "") if market_context else ""),
            "technical": str(market_context.get("snapshot", "") if market_context else ""),
        },
        "cost_usd": settings.debate_per_call_budget_usd,
        "cached": False,
    }

    if budget is not None:
        await budget.record(actual_cost_usd=settings.debate_per_call_budget_usd)
    await _set_cached(redis, cache_key, payload)
    return payload


async def fetch_debate_signals_batch(
    symbols: list[str],
    *,
    trade_date: str | None = None,
    settings: Settings | None = None,
    redis: Any | None = None,
    budget: Any | None = None,
    market_context_by_symbol: dict[str, dict[str, Any]] | None = None,
    concurrency: int = 1,
) -> dict[str, dict]:
    """Run ``fetch_debate_signal`` across ``symbols``.

    Concurrency defaults to 1 because each ticker triggers three LLM calls.
    Failed lookups (returning ``None``) are dropped from the output map.
    """
    if not symbols:
        return {}

    sem = asyncio.Semaphore(max(1, concurrency))
    out: dict[str, dict] = {}
    ctx_map = market_context_by_symbol or {}

    async def _one(sym: str) -> None:
        async with sem:
            payload = await fetch_debate_signal(
                sym,
                trade_date=trade_date,
                settings=settings,
                redis=redis,
                budget=budget,
                market_context=ctx_map.get(sym.upper()),
            )
            if payload is not None:
                out[sym.upper()] = payload

    await asyncio.gather(*(_one(s) for s in symbols))
    return out


__all__ = [
    "fetch_debate_signal",
    "fetch_debate_signals_batch",
    "CACHE_PREFIX",
    "BUDGET_PREFIX",
]
