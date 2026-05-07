"""Tests for ``agents/oracle/data_sources/debate.py``.

The debate module talks to Claude via ``ClaudeClient.chat`` which is
LLM-driven and slow. Tests stub ``_think_json`` so we exercise the
wrapper logic (cache, budget, error isolation, normalization, batch)
without touching any LLM.
"""

from __future__ import annotations

import json

import pytest

from oracle.data_sources import debate  # type: ignore[import-not-found]
from shared.budget import BudgetTracker  # type: ignore[import-not-found]
from tests._fakes import FakeRedis


class _Settings:
    """Duck-typed Settings the wrapper consumes."""

    debate_enabled = True
    debate_analyst_model = "claude-sonnet-4-6"
    debate_judge_model = "claude-opus-4-7"
    debate_top_n = 3
    debate_daily_budget_usd = 5.0
    debate_per_call_budget_usd = 0.30


def _stub_outputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    bull: dict | None = None,
    bear: dict | None = None,
    verdict: dict | None = None,
) -> dict[str, int]:
    """Patch ``debate._think_json`` to return canned responses by system prompt.

    Returns a dict counter so tests can assert call counts.
    """
    counts = {"bull": 0, "bear": 0, "judge": 0}
    bull = bull or {
        "thesis": "AAPL services growth + buybacks support upside",
        "key_drivers": ["services", "buybacks", "valuation"],
        "primary_risk": "iPhone refresh cycle slowing",
        "conviction": 0.7,
    }
    bear = bear or {
        "thesis": "Margin compression + China weakness threaten earnings",
        "key_drivers": ["china", "margin", "competition"],
        "primary_risk": "services beat",
        "conviction": 0.5,
    }
    verdict = verdict or {
        "decision": "BUY",
        "winner": "bull",
        "rationale": "Bull case stronger on multiples and capital return.",
        "conviction": 0.65,
    }

    async def fake(client, system, user_prompt):  # noqa: ARG001
        if "bull analyst" in system:
            counts["bull"] += 1
            return bull
        if "bear analyst" in system:
            counts["bear"] += 1
            return bear
        counts["judge"] += 1
        return verdict

    monkeypatch.setattr(debate, "_think_json", fake)
    return counts


@pytest.mark.asyncio
async def test_disabled_returns_none() -> None:
    settings = _Settings()
    settings.debate_enabled = False
    out = await debate.fetch_debate_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=FakeRedis()
    )
    assert out is None


@pytest.mark.asyncio
async def test_propagate_returns_normalized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _stub_outputs(monkeypatch)
    redis = FakeRedis()
    out = await debate.fetch_debate_signal(
        "aapl", trade_date="2026-05-07", settings=_Settings(), redis=redis
    )
    assert out is not None
    assert out["symbol"] == "AAPL"
    assert out["decision"] == "BUY"
    assert out["debate_log"]["winner"] == "bull"
    assert out["debate_log"]["bull"]
    assert out["debate_log"]["bear"]
    assert 0.0 <= out["conviction"] <= 1.0
    assert out["cached"] is False
    # 1 bull + 1 bear + 1 judge call.
    assert counts == {"bull": 1, "bear": 1, "judge": 1}
    # Cache populated.
    raw = await redis.get(debate._cache_key("AAPL", "2026-05-07"))
    assert raw is not None
    assert json.loads(raw)["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_cache_hit_skips_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = _stub_outputs(monkeypatch)
    redis = FakeRedis()
    settings = _Settings()
    await debate.fetch_debate_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=redis
    )
    assert counts == {"bull": 1, "bear": 1, "judge": 1}
    out = await debate.fetch_debate_signal(
        "AAPL", trade_date="2026-05-07", settings=settings, redis=redis
    )
    assert out is not None
    assert out["cached"] is True
    # No additional LLM calls.
    assert counts == {"bull": 1, "bear": 1, "judge": 1}


@pytest.mark.asyncio
async def test_budget_exhausted_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = _stub_outputs(monkeypatch)
    settings = _Settings()
    redis = FakeRedis()
    budget = BudgetTracker(redis, key_prefix="atlas:budget:debate-test")
    # Pre-spend the cap.
    await budget.record(settings.debate_daily_budget_usd + 0.01)
    out = await debate.fetch_debate_signal(
        "AAPL",
        trade_date="2026-05-07",
        settings=settings,
        redis=redis,
        budget=budget,
    )
    assert out is None
    assert counts == {"bull": 0, "bear": 0, "judge": 0}


@pytest.mark.asyncio
async def test_analyst_phase_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If either analyst raises, the wrapper isolates the failure."""

    async def explode(client, system, user_prompt):  # noqa: ARG001
        raise RuntimeError("bull went down")

    monkeypatch.setattr(debate, "_think_json", explode)
    out = await debate.fetch_debate_signal(
        "AAPL", trade_date="2026-05-07", settings=_Settings(), redis=FakeRedis()
    )
    assert out is None


@pytest.mark.asyncio
async def test_judge_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Judge failure also surfaces as None — never partial output."""
    state = {"calls": 0}

    async def selective(client, system, user_prompt):  # noqa: ARG001
        state["calls"] += 1
        if "judge" in system:
            raise RuntimeError("judge down")
        return {
            "thesis": "x",
            "key_drivers": [],
            "primary_risk": "y",
            "conviction": 0.5,
        }

    monkeypatch.setattr(debate, "_think_json", selective)
    out = await debate.fetch_debate_signal(
        "AAPL", trade_date="2026-05-07", settings=_Settings(), redis=FakeRedis()
    )
    assert out is None
    # Bull + bear ran, judge attempted.
    assert state["calls"] == 3


def test_decision_normalization() -> None:
    assert debate._normalize_decision("BUY") == "BUY"
    assert debate._normalize_decision("buy now") == "BUY"
    assert debate._normalize_decision("we should go long") == "BUY"
    assert debate._normalize_decision("sell") == "SELL"
    assert debate._normalize_decision("short setup") == "SELL"
    assert debate._normalize_decision("") == "HOLD"
    assert debate._normalize_decision(None) == "HOLD"
    assert debate._normalize_decision("hold for now") == "HOLD"


def test_winner_normalization() -> None:
    assert debate._normalize_winner("bull") == "bull"
    assert debate._normalize_winner("BULL CASE WINS") == "bull"
    assert debate._normalize_winner("bear") == "bear"
    assert debate._normalize_winner("Bears clearly stronger") == "bear"
    assert debate._normalize_winner("") == "neutral"
    assert debate._normalize_winner(None) == "neutral"
    assert debate._normalize_winner("split decision") == "neutral"


@pytest.mark.asyncio
async def test_batch_runs_each_ticker_drops_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"failed": False}

    async def selective(client, system, user_prompt):  # noqa: ARG001
        if "MSFT" in user_prompt and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("MSFT flaky")
        if "bull analyst" in system:
            return {"thesis": "x", "key_drivers": [], "primary_risk": "y", "conviction": 0.6}
        if "bear analyst" in system:
            return {"thesis": "x", "key_drivers": [], "primary_risk": "y", "conviction": 0.4}
        return {"decision": "BUY", "winner": "bull", "rationale": "ok", "conviction": 0.55}

    monkeypatch.setattr(debate, "_think_json", selective)
    out = await debate.fetch_debate_signals_batch(
        ["AAPL", "MSFT"],
        trade_date="2026-05-07",
        settings=_Settings(),
        redis=FakeRedis(),
    )
    # AAPL succeeds; MSFT was made to fail on its first analyst call.
    assert "AAPL" in out
    assert "MSFT" not in out


@pytest.mark.asyncio
async def test_market_context_passes_into_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_prompts: list[str] = []

    async def capture(client, system, user_prompt):  # noqa: ARG001
        seen_prompts.append(user_prompt)
        if "bull analyst" in system:
            return {"thesis": "x", "key_drivers": [], "primary_risk": "y", "conviction": 0.5}
        if "bear analyst" in system:
            return {"thesis": "x", "key_drivers": [], "primary_risk": "y", "conviction": 0.5}
        return {"decision": "HOLD", "winner": "neutral", "rationale": "tied", "conviction": 0.4}

    monkeypatch.setattr(debate, "_think_json", capture)
    await debate.fetch_debate_signal(
        "AAPL",
        trade_date="2026-05-07",
        settings=_Settings(),
        redis=FakeRedis(),
        market_context={
            "score": 0.42,
            "suggested_direction": "LONG",
            "snapshot": {"rsi": 58},
        },
    )
    # Bull + bear see the same context block.
    assert any("Screener score: +0.42" in p for p in seen_prompts)
    assert any("LONG" in p for p in seen_prompts)
