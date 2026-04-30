"""Claude Agent SDK wrapper — drop-in replacement for OpenRouterClient.

Auth is inherited from the host's ``~/.claude/`` Claude Code session — no
``ANTHROPIC_API_KEY`` is read or required. Each call is a one-shot ``query``
through the SDK, with input/output tokens persisted to the Postgres
``llm_calls`` table for cost tracking parity with Jarvis.

Public ``chat()`` signature mirrors ``OpenRouterClient.chat`` so swapping is a
single import change in :mod:`base_agent`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .db import get_session

logger = logging.getLogger(__name__)


# Anthropic published per-million-token pricing (USD).
# Source: https://www.anthropic.com/pricing  (input | output)
# Subscription auth (Claude Code) bills against quota, but cost_usd_estimate
# stays useful for relative agent attribution + budget telemetry.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-sonnet-4-7": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-6": (1.0, 5.0),
}
_DEFAULT_PRICING = (3.0, 15.0)


@dataclass(frozen=True)
class _CallUsage:
    input_tokens: int
    output_tokens: int


def _estimate_cost_usd(model: str, usage: _CallUsage) -> float:
    """Compute USD cost for one call using published per-MTok pricing."""
    in_price, out_price = PRICING_USD_PER_MTOK.get(model, _DEFAULT_PRICING)
    return (usage.input_tokens / 1_000_000) * in_price + (
        usage.output_tokens / 1_000_000
    ) * out_price


def _strip_markdown_fences(raw: str) -> str:
    """Tolerate ```json ... ``` wrappers around model output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    return raw.strip()


def _format_messages_as_prompt(
    messages: list[dict],
    response_format: dict | None,
) -> str:
    """Flatten a chat-style message list to a single user prompt string.

    The SDK ``query()`` API takes one prompt; multi-turn semantics from the
    OpenAI-compatible shape are preserved by labelled concatenation.
    """
    parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").upper()
        content = m.get("content") or ""
        parts.append(f"[{role}]\n{content}")
    if response_format and response_format.get("type") == "json_object":
        parts.append(
            "[INSTRUCTION]\nRespond with a single JSON object only. "
            "No prose, no markdown fences."
        )
    return "\n\n".join(parts)


def _extract_usage(msg: Any) -> _CallUsage:
    """Pull input/output token counts from a SDK ``ResultMessage``."""
    usage = getattr(msg, "usage", None) or {}
    in_tok = int(usage.get("input_tokens", 0) or 0)
    # Cache reads count as input for billing; include them in input total.
    in_tok += int(usage.get("cache_read_input_tokens", 0) or 0)
    in_tok += int(usage.get("cache_creation_input_tokens", 0) or 0)
    out_tok = int(usage.get("output_tokens", 0) or 0)
    return _CallUsage(input_tokens=in_tok, output_tokens=out_tok)


_LLM_CALLS_DDL = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id UUID PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd_estimate NUMERIC(12, 6) NOT NULL DEFAULT 0
)
"""

_LLM_CALLS_INSERT = """
INSERT INTO llm_calls (id, ts, agent_id, model, input_tokens, output_tokens, cost_usd_estimate)
VALUES (:id, :ts, :agent, :model, :in_tok, :out_tok, :cost)
"""


async def _persist_call(
    *,
    agent_id: str,
    model: str,
    usage: _CallUsage,
    cost_usd: float,
) -> None:
    """Best-effort write of one call to ``llm_calls``. Failures are warnings."""
    try:
        async with get_session() as sess:
            await sess.execute(
                text(_LLM_CALLS_INSERT),
                {
                    "id": str(uuid.uuid4()),
                    "ts": datetime.utcnow(),
                    "agent": agent_id,
                    "model": model,
                    "in_tok": usage.input_tokens,
                    "out_tok": usage.output_tokens,
                    "cost": cost_usd,
                },
            )
            await sess.commit()
    except Exception as exc:  # noqa: BLE001 — log-and-continue is intentional
        logger.warning(
            "[%s] Failed to persist llm_call (%s): %s", agent_id, model, exc
        )


class ClaudeClient:
    """Thin async wrapper over ``claude_agent_sdk.query``.

    Drop-in for ``OpenRouterClient``: same ``chat()`` signature, same return
    shape (assistant text as ``str``). No ``api_key`` argument — auth comes
    from the host's Claude Code session.
    """

    def __init__(self, model: str, agent_id: str):
        self.model = model
        self.agent_id = agent_id

    async def chat(  # noqa: PLR0913 — mirrors OpenRouterClient.chat
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        retries: int = 3,
    ) -> str:
        """Send a chat-style message list, return the assistant's text.

        ``temperature`` and ``max_tokens`` are accepted for API parity but the
        SDK does not forward them; Claude Code's defaults are used. Token
        usage and cost estimate are persisted to ``llm_calls``.
        """
        # Local import keeps test environments without the SDK importable.
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        prompt = _format_messages_as_prompt(messages, response_format)
        opts = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system,
            permission_mode="bypassPermissions",
        )

        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                chunks: list[str] = []
                usage = _CallUsage(input_tokens=0, output_tokens=0)
                async for msg in query(prompt=prompt, options=opts):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock) and block.text:
                                chunks.append(block.text)
                    elif isinstance(msg, ResultMessage):
                        usage = _extract_usage(msg)

                cost = _estimate_cost_usd(self.model, usage)
                await _persist_call(
                    agent_id=self.agent_id,
                    model=self.model,
                    usage=usage,
                    cost_usd=cost,
                )
                raw = "".join(chunks).strip()
                if response_format and response_format.get("type") == "json_object":
                    raw = _strip_markdown_fences(raw)
                return raw
            except Exception as exc:  # noqa: BLE001 — retry layer
                last_error = exc
                wait = 2**attempt
                logger.warning(
                    "[%s] Claude SDK error (attempt %d/%d): %s — retry in %ds",
                    self.agent_id,
                    attempt + 1,
                    retries,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"[{self.agent_id}] Claude SDK call failed after {retries} attempts: {last_error}"
        )

    async def close(self) -> None:
        """Symmetry with OpenRouterClient.close — nothing to release."""
        return None


__all__ = [
    "ClaudeClient",
    "PRICING_USD_PER_MTOK",
    "_LLM_CALLS_DDL",
]
