"""Tests for ``agents/oracle/data_sources/tauric_signal.py``.

The real ``tradingagents`` propagate is LLM-driven and slow; tests stub
``_build_graph`` so we exercise the wrapper logic (cache, budget, error
isolation, normalization) without touching any LLM.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from oracle.data_sources import tauric_signal  # type: ignore[import-not-found]
from shared.budget import BudgetTracker  # type: ignore[import-not-found]
from tests._fakes import FakeRedis


class _StubState:
    def __init__(
        self,
        bull: str = "bullish thesis",
        bear: str = "bearish thesis",
        judge: str = "BUY recommended",
    ) -> None:
        self.investment_debate_state = {
            "bull_history": bull,
            "bear_history": bear,
            "judge_decision": judge,
        }
        self.fundamentals_report = "fundamentals body"
        self.sentiment_report = "sentiment body"
        self.news_report = "news body"
        self.market_report = "technical body"


class _StubGraph:
    """Minimal TradingAgentsGraph surrogate."""

    def __init__(self, decision: str = "BUY", state: Any | None = None) -> None:
        self._decision = decision
        self._state = state or _StubState()
        self.calls: list[tuple[str, str]] = []

    def propagate(self, ticker: str, trade_date: str):
        self.calls.append((ticker, trade_date))
        return self._state, self._decision


class _Settings:
    """Minimal Settings duck-type the wrapper consumes."""

    tauric_enabled = True
    tauric_llm_provider = "openrouter"
    tauric_deep_llm = "anthropic/claude-opus-4-7"
    tauric_quick_llm = "anthropic/claude-haiku-4-5-20251001"
    tauric_max_debate_rounds = 1
    tauric_max_risk_rounds = 1
    tauric_max_recur_limit = 25
    tauric_reasoning_effort = "medium"
    tauric_daily_budget_usd = 5.0
    tauric_per_call_budget_usd = 0.30


@pytest.fixture
def stub_graph(monkeypatch: pytest.MonkeyPatch) -> _StubGraph:
    graph = _StubGraph(decision="BUY")
    monkeypatch.setattr(tauric_signal, "_build_graph", lambda settings: graph)
    return graph


@pytest.mark.asyncio
async def test_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _Settings()
    settings.tauric_enabled = False
    out = await tauric_signal.fetch_tauric_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=FakeRedis()
    )
    assert out is None


@pytest.mark.asyncio
async def test_propagate_returns_normalized_payload(
    stub_graph: _StubGraph,
) -> None:
    settings = _Settings()
    redis = FakeRedis()
    out = await tauric_signal.fetch_tauric_signal(
        "aapl", trade_date="2026-05-07", settings=settings, redis=redis
    )
    assert out is not None
    assert out["symbol"] == "AAPL"
    assert out["decision"] == "BUY"
    assert out["debate_log"]["bull"]
    assert out["debate_log"]["bear"]
    assert out["debate_log"]["winner"] == "bull"
    assert out["analyst_reports"]["fundamentals"] == "fundamentals body"
    assert out["cached"] is False
    # Cache populated.
    raw = await redis.get(tauric_signal._cache_key("AAPL", "2026-05-07"))
    assert raw is not None
    assert json.loads(raw)["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_cache_hit_returns_without_calling_graph(
    stub_graph: _StubGraph,
) -> None:
    settings = _Settings()
    redis = FakeRedis()
    # Prime cache.
    await tauric_signal.fetch_tauric_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=redis
    )
    assert len(stub_graph.calls) == 1
    # Second call should NOT hit propagate.
    out = await tauric_signal.fetch_tauric_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=redis
    )
    assert out is not None
    assert out["cached"] is True
    assert len(stub_graph.calls) == 1


@pytest.mark.asyncio
async def test_budget_exhausted_returns_none(stub_graph: _StubGraph) -> None:
    settings = _Settings()
    redis = FakeRedis()
    budget = BudgetTracker(redis, key_prefix="atlas:budget:tauric-test")
    # Pre-spend the entire daily cap.
    await budget.record(settings.tauric_daily_budget_usd + 0.01)
    out = await tauric_signal.fetch_tauric_signal(
        "AAPL",
        trade_date="2026-05-07",
        settings=settings,
        redis=redis,
        budget=budget,
    )
    assert out is None
    assert stub_graph.calls == []


@pytest.mark.asyncio
async def test_propagate_raises_returns_none_no_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tauric failures must NEVER bubble up — Oracle treats it as augment-only."""

    class _BoomGraph:
        def propagate(self, ticker: str, trade_date: str):
            raise RuntimeError("LLM exploded")

    monkeypatch.setattr(tauric_signal, "_build_graph", lambda settings: _BoomGraph())
    settings = _Settings()
    out = await tauric_signal.fetch_tauric_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=FakeRedis()
    )
    assert out is None


@pytest.mark.asyncio
async def test_decision_normalization() -> None:
    assert tauric_signal._normalize_decision("BUY") == "BUY"
    assert tauric_signal._normalize_decision("sell now") == "SELL"
    assert tauric_signal._normalize_decision("we should go long") == "BUY"
    assert tauric_signal._normalize_decision("short setup") == "SELL"
    assert tauric_signal._normalize_decision("") == "HOLD"
    assert tauric_signal._normalize_decision(None) == "HOLD"


@pytest.mark.asyncio
async def test_batch_runs_each_ticker_and_skips_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _Settings()
    redis = FakeRedis()
    success_graph = _StubGraph(decision="BUY")

    class _Selector:
        def propagate(self, ticker: str, trade_date: str):
            if ticker == "MSFT":
                raise RuntimeError("flaky")
            return success_graph._state, "BUY"

    monkeypatch.setattr(tauric_signal, "_build_graph", lambda settings: _Selector())
    out = await tauric_signal.fetch_tauric_signals_batch(
        ["AAPL", "MSFT"],
        trade_date="2026-05-07",
        settings=settings,
        redis=redis,
    )
    assert "AAPL" in out
    assert "MSFT" not in out
