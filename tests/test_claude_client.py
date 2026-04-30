"""ClaudeClient unit tests — SDK is mocked, llm_calls write is captured.

Scope:
* ``chat()`` returns assembled assistant text from a stream of mock messages.
* Token usage is extracted from ``ResultMessage.usage`` and persisted.
* JSON ``response_format`` strips markdown fences.
* Cost estimate uses the published per-MTok pricing table.
"""
from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.claude_client import (
    ClaudeClient,
    PRICING_USD_PER_MTOK,
    _CallUsage,
    _estimate_cost_usd,
    _format_messages_as_prompt,
    _strip_markdown_fences,
)


# --------------------------- pure-function tests ---------------------------


def test_estimate_cost_uses_published_pricing() -> None:
    # Arrange — Sonnet pricing: $3/MTok input, $15/MTok output
    usage = _CallUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    # Act
    cost = _estimate_cost_usd("claude-sonnet-4-6", usage)

    # Assert
    assert cost == pytest.approx(18.0)


def test_estimate_cost_unknown_model_falls_back_to_sonnet_tier() -> None:
    usage = _CallUsage(input_tokens=1_000_000, output_tokens=0)
    cost = _estimate_cost_usd("some-future-model", usage)
    assert cost == pytest.approx(3.0)


def test_estimate_cost_haiku_cheapest_tier() -> None:
    usage = _CallUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = _estimate_cost_usd("claude-haiku-4-5", usage)
    assert cost == pytest.approx(6.0)


def test_pricing_table_covers_required_models() -> None:
    """Every model wired in Settings must have published pricing."""
    required = {
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "claude-haiku-4-5",
    }
    assert required.issubset(PRICING_USD_PER_MTOK.keys())


def test_strip_markdown_fences_removes_json_block() -> None:
    raw = '```json\n{"key": "value"}\n```'
    assert _strip_markdown_fences(raw) == '{"key": "value"}'


def test_strip_markdown_fences_passthrough_when_no_fence() -> None:
    raw = '{"key": "value"}'
    assert _strip_markdown_fences(raw) == '{"key": "value"}'


def test_format_messages_labels_roles() -> None:
    messages = [
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "pong"},
    ]
    prompt = _format_messages_as_prompt(messages, response_format=None)
    assert "[USER]" in prompt
    assert "[ASSISTANT]" in prompt
    assert "ping" in prompt and "pong" in prompt


def test_format_messages_appends_json_instruction_when_requested() -> None:
    messages = [{"role": "user", "content": "give me a json"}]
    prompt = _format_messages_as_prompt(
        messages, response_format={"type": "json_object"}
    )
    assert "JSON object" in prompt


# --------------------------- chat() integration ---------------------------


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeAssistantMessage:
    content: list[Any]


@dataclass
class _FakeResultMessage:
    usage: dict[str, Any]


def _install_fake_sdk(messages: list[Any]) -> dict[str, Any]:
    """Replace ``claude_agent_sdk`` in ``sys.modules`` with a fake.

    The fake exposes the names ``ClaudeClient.chat`` imports locally and a
    ``query()`` async generator that yields ``messages`` in order.
    """
    fake = types.ModuleType("claude_agent_sdk")
    fake.AssistantMessage = _FakeAssistantMessage  # type: ignore[attr-defined]
    fake.TextBlock = _FakeTextBlock  # type: ignore[attr-defined]
    fake.ResultMessage = _FakeResultMessage  # type: ignore[attr-defined]

    class _FakeOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    fake.ClaudeAgentOptions = _FakeOptions  # type: ignore[attr-defined]

    async def _fake_query(prompt: str, options: Any):  # noqa: ARG001
        for m in messages:
            yield m

    fake.query = _fake_query  # type: ignore[attr-defined]
    sys.modules["claude_agent_sdk"] = fake
    return {"prompt_seen": []}


@pytest.mark.asyncio
async def test_chat_returns_concatenated_assistant_text() -> None:
    # Arrange — fake SDK yields one assistant message with two blocks, one result
    fake_messages = [
        _FakeAssistantMessage(
            content=[_FakeTextBlock(text="hello "), _FakeTextBlock(text="world")]
        ),
        _FakeResultMessage(usage={"input_tokens": 10, "output_tokens": 5}),
    ]
    _install_fake_sdk(fake_messages)
    client = ClaudeClient(model="claude-sonnet-4-6", agent_id="oracle")

    persist_mock = AsyncMock()
    with patch("shared.claude_client._persist_call", persist_mock):
        # Act
        out = await client.chat([{"role": "user", "content": "hi"}])

    # Assert
    assert out == "hello world"
    persist_mock.assert_awaited_once()
    kwargs = persist_mock.await_args.kwargs
    assert kwargs["agent_id"] == "oracle"
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["usage"].input_tokens == 10
    assert kwargs["usage"].output_tokens == 5
    # Sonnet: 10/1M*3 + 5/1M*15
    assert kwargs["cost_usd"] == pytest.approx(10 * 3 / 1_000_000 + 5 * 15 / 1_000_000)


@pytest.mark.asyncio
async def test_chat_persists_call_when_db_session_works() -> None:
    """End-to-end: _persist_call must INSERT into llm_calls with the right shape."""
    fake_messages = [
        _FakeAssistantMessage(content=[_FakeTextBlock(text="ok")]),
        _FakeResultMessage(usage={"input_tokens": 100, "output_tokens": 20}),
    ]
    _install_fake_sdk(fake_messages)

    captured: dict[str, Any] = {}

    class _FakeSession:
        async def execute(self, stmt: Any, params: Any) -> None:
            captured["sql"] = str(stmt)
            captured["params"] = params

        async def commit(self) -> None:
            captured["committed"] = True

        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

    fake_session = _FakeSession()

    def _fake_get_session() -> _FakeSession:
        return fake_session

    client = ClaudeClient(model="claude-haiku-4-5", agent_id="guardian")
    with patch("shared.claude_client.get_session", _fake_get_session):
        out = await client.chat([{"role": "user", "content": "go"}])

    assert out == "ok"
    assert captured["committed"] is True
    assert "INSERT INTO llm_calls" in captured["sql"]
    p = captured["params"]
    assert p["agent"] == "guardian"
    assert p["model"] == "claude-haiku-4-5"
    assert p["in_tok"] == 100
    assert p["out_tok"] == 20
    # Haiku: 100/1M*1 + 20/1M*5
    assert p["cost"] == pytest.approx(100 / 1_000_000 + 20 * 5 / 1_000_000)


@pytest.mark.asyncio
async def test_chat_strips_markdown_when_json_format_requested() -> None:
    fake_messages = [
        _FakeAssistantMessage(
            content=[_FakeTextBlock(text='```json\n{"a": 1}\n```')]
        ),
        _FakeResultMessage(usage={"input_tokens": 1, "output_tokens": 1}),
    ]
    _install_fake_sdk(fake_messages)
    client = ClaudeClient(model="claude-sonnet-4-6", agent_id="oracle")
    with patch("shared.claude_client._persist_call", AsyncMock()):
        out = await client.chat(
            [{"role": "user", "content": "json please"}],
            response_format={"type": "json_object"},
        )
    assert out == '{"a": 1}'


@pytest.mark.asyncio
async def test_chat_persist_failure_does_not_break_caller() -> None:
    """A DB outage during cost-tracking must not crash the chat call."""
    fake_messages = [
        _FakeAssistantMessage(content=[_FakeTextBlock(text="alive")]),
        _FakeResultMessage(usage={"input_tokens": 0, "output_tokens": 0}),
    ]
    _install_fake_sdk(fake_messages)

    def _broken_get_session() -> None:
        raise RuntimeError("db unreachable")

    client = ClaudeClient(model="claude-sonnet-4-6", agent_id="sage")
    with patch("shared.claude_client.get_session", _broken_get_session):
        out = await client.chat([{"role": "user", "content": "ping"}])
    assert out == "alive"


@pytest.mark.asyncio
async def test_chat_retries_on_sdk_exception_then_succeeds() -> None:
    """Transient SDK error → retry → success."""
    call_count = {"n": 0}

    async def _flaky_query(prompt: str, options: Any):  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient")
        yield _FakeAssistantMessage(content=[_FakeTextBlock(text="recovered")])
        yield _FakeResultMessage(usage={"input_tokens": 1, "output_tokens": 1})

    fake = types.ModuleType("claude_agent_sdk")
    fake.AssistantMessage = _FakeAssistantMessage  # type: ignore[attr-defined]
    fake.TextBlock = _FakeTextBlock  # type: ignore[attr-defined]
    fake.ResultMessage = _FakeResultMessage  # type: ignore[attr-defined]
    fake.ClaudeAgentOptions = lambda **kw: types.SimpleNamespace(**kw)  # type: ignore[attr-defined]
    fake.query = _flaky_query  # type: ignore[attr-defined]
    sys.modules["claude_agent_sdk"] = fake

    client = ClaudeClient(model="claude-sonnet-4-6", agent_id="trader")
    with (
        patch("shared.claude_client._persist_call", AsyncMock()),
        patch("shared.claude_client.asyncio.sleep", AsyncMock()),
    ):
        out = await client.chat([{"role": "user", "content": "go"}], retries=3)
    assert out == "recovered"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_close_is_noop() -> None:
    client = ClaudeClient(model="claude-sonnet-4-6", agent_id="oracle")
    # Must not raise
    await client.close()
