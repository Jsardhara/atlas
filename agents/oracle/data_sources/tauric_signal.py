"""Tauric (TradingAgents) signal data source.

Wraps :class:`tradingagents.graph.trading_graph.TradingAgentsGraph` and
returns a flat dict that Oracle merges with its existing screener output.

Design notes:

* **Cache by (ticker, trade_date)**: a debate run for AAPL on
  ``2026-05-07`` is deterministic enough that we never re-spend on the
  same day. Cache keys live in Redis with a 24h TTL.
* **Daily budget cap**: every call routes through
  :class:`agents.shared.budget.BudgetTracker`. Cap is configurable via
  ``Settings.tauric_daily_budget_usd``. When the cap is hit the wrapper
  returns ``None`` instead of raising — Oracle treats Tauric as an
  *augment* layer, not a hard dependency.
* **Provider routing**: Tauric talks to ``openrouter`` so the same
  Anthropic Claude account that powers ATLAS handles the debate.
* **Failure isolation**: any Tauric error is caught and logged. Oracle's
  primary screener output is unaffected.

Returned dict shape::

    {
        "symbol": "AAPL",
        "trade_date": "2026-05-07",
        "decision": "BUY" | "SELL" | "HOLD",
        "rationale": "<final analyst summary, possibly truncated>",
        "debate_log": {"bull": "...", "bear": "...", "winner": "bull"},
        "analyst_reports": {
            "fundamentals": "...", "sentiment": "...",
            "news": "...", "technical": "...",
        },
        "cost_usd": <estimated>,
        "cached": <bool>,
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from shared.config import Settings  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

CACHE_PREFIX = "atlas:tauric:cache"
BUDGET_PREFIX = "atlas:budget:tauric"
CACHE_TTL_SEC = 60 * 60 * 24  # 24h


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _cache_key(symbol: str, trade_date: str) -> str:
    return f"{CACHE_PREFIX}:{symbol.upper()}:{trade_date}"


def _build_graph_config(settings: Settings) -> Any | None:
    """Build a TradingAgentsConfig instance. Returns None on import failure."""
    try:
        from tradingagents.default_config import (  # type: ignore[import-not-found]
            TradingAgentsConfig,
        )
    except ImportError as exc:
        logger.warning("tradingagents not installed: %s", exc)
        return None
    return TradingAgentsConfig(
        llm_provider=settings.tauric_llm_provider,
        deep_think_llm=settings.tauric_deep_llm,
        quick_think_llm=settings.tauric_quick_llm,
        max_debate_rounds=settings.tauric_max_debate_rounds,
        max_risk_discuss_rounds=settings.tauric_max_risk_rounds,
        max_recur_limit=settings.tauric_max_recur_limit,
        reasoning_effort=settings.tauric_reasoning_effort,
    )


def _build_graph(settings: Settings) -> Any | None:
    """Instantiate TradingAgentsGraph. Returns None on any setup failure."""
    cfg = _build_graph_config(settings)
    if cfg is None:
        return None
    try:
        from tradingagents.graph.trading_graph import (  # type: ignore[import-not-found]
            TradingAgentsGraph,
        )
    except ImportError as exc:
        logger.warning("tradingagents.graph import failed: %s", exc)
        return None
    try:
        return TradingAgentsGraph(config=cfg)
    except Exception as exc:  # noqa: BLE001 — third-party may raise anything
        logger.warning("TradingAgentsGraph construction failed: %s", exc)
        return None


def _normalize_decision(decision: Any) -> str:
    """Squash arbitrary string output into BUY/SELL/HOLD."""
    if not decision:
        return "HOLD"
    text = str(decision).strip().upper()
    if "BUY" in text or "LONG" in text:
        return "BUY"
    if "SELL" in text or "SHORT" in text:
        return "SELL"
    return "HOLD"


def _extract_debate(state: Any) -> dict[str, str]:
    """Pull bull/bear summaries out of AgentState. Defensive — fields vary."""
    try:
        debate = getattr(state, "investment_debate_state", None) or {}
        if isinstance(debate, dict):
            bull = str(debate.get("bull_history", "") or debate.get("bull", "") or "")
            bear = str(debate.get("bear_history", "") or debate.get("bear", "") or "")
            judge = str(debate.get("judge_decision", "") or "")
            winner = "bull" if "BUY" in judge.upper() else (
                "bear" if "SELL" in judge.upper() else "neutral"
            )
            return {"bull": bull[:2000], "bear": bear[:2000], "winner": winner}
    except Exception as exc:  # noqa: BLE001
        logger.warning("tauric debate extract failed: %s", exc)
    return {"bull": "", "bear": "", "winner": "unknown"}


def _extract_reports(state: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for field, label in [
        ("fundamentals_report", "fundamentals"),
        ("sentiment_report", "sentiment"),
        ("news_report", "news"),
        ("market_report", "technical"),
    ]:
        try:
            value = getattr(state, field, "") or ""
            out[label] = str(value)[:2000]
        except Exception:  # noqa: BLE001
            out[label] = ""
    return out


async def _get_cached(redis: Any | None, key: str) -> dict | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tauric cache read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        cached = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("tauric cache value not valid JSON: %s", exc)
        return None
    cached["cached"] = True
    return cached


async def _set_cached(redis: Any | None, key: str, payload: dict) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(payload), ex=CACHE_TTL_SEC)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tauric cache write failed: %s", exc)


async def fetch_tauric_signal(
    symbol: str,
    trade_date: str | None = None,
    *,
    settings: Settings | None = None,
    redis: Any | None = None,
    budget: Any | None = None,
) -> dict | None:
    """Run TradingAgents for ``symbol`` on ``trade_date`` (default: today UTC).

    Returns a flat dict on success, or ``None`` when:

    * ``Settings.tauric_enabled`` is False
    * the ``tradingagents`` package is missing
    * the daily budget cap is exhausted
    * the propagate call raises (logged, never re-raised)
    """
    from .. import data_sources  # noqa: F401 — package init side-effect (logger setup)

    if settings is None:
        from shared.config import get_settings  # type: ignore[import-not-found]

        settings = get_settings()

    if not settings.tauric_enabled:
        return None

    date_str = trade_date or _today_utc()
    cache_key = _cache_key(symbol, date_str)

    cached = await _get_cached(redis, cache_key)
    if cached is not None:
        logger.info("[tauric] cache hit %s/%s", symbol, date_str)
        return cached

    if budget is not None:
        affordable = await budget.can_afford(
            estimated_cost_usd=settings.tauric_per_call_budget_usd,
            daily_cap=settings.tauric_daily_budget_usd,
        )
        if not affordable:
            logger.info(
                "[tauric] budget exhausted; skipping %s (cap=%.2f)",
                symbol, settings.tauric_daily_budget_usd,
            )
            return None

    graph = _build_graph(settings)
    if graph is None:
        return None

    try:
        state, decision = await asyncio.to_thread(graph.propagate, symbol, date_str)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tauric] propagate failed for %s: %s", symbol, exc)
        return None

    payload: dict = {
        "symbol": symbol.upper(),
        "trade_date": date_str,
        "decision": _normalize_decision(decision),
        "rationale": str(decision)[:2000],
        "debate_log": _extract_debate(state),
        "analyst_reports": _extract_reports(state),
        "cost_usd": settings.tauric_per_call_budget_usd,
        "cached": False,
    }

    if budget is not None:
        await budget.record(actual_cost_usd=settings.tauric_per_call_budget_usd)
    await _set_cached(redis, cache_key, payload)
    return payload


async def fetch_tauric_signals_batch(
    symbols: list[str],
    *,
    trade_date: str | None = None,
    settings: Settings | None = None,
    redis: Any | None = None,
    budget: Any | None = None,
    concurrency: int = 1,
) -> dict[str, dict]:
    """Run Tauric across a list of tickers and return ``{symbol: payload}``.

    Concurrency defaults to 1 because Tauric is LLM-heavy and budget-capped.
    Failed lookups (None) are dropped from the output map.
    """
    if not symbols:
        return {}

    sem = asyncio.Semaphore(max(1, concurrency))
    out: dict[str, dict] = {}

    async def _one(sym: str) -> None:
        async with sem:
            payload = await fetch_tauric_signal(
                sym,
                trade_date=trade_date,
                settings=settings,
                redis=redis,
                budget=budget,
            )
            if payload is not None:
                out[sym.upper()] = payload

    await asyncio.gather(*(_one(s) for s in symbols))
    return out


__all__ = [
    "fetch_tauric_signal",
    "fetch_tauric_signals_batch",
    "CACHE_PREFIX",
    "BUDGET_PREFIX",
]
