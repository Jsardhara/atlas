"""Guardian — Trade confirmation and risk critique agent."""
import asyncio
import json
import logging

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import AgentID, AtlasMessage, MessageType

from .validators.hard_rules import validate_hard_rules

logger = logging.getLogger(__name__)

PERSONALITY = """You are Guardian, a risk-obsessed, skeptical trade validator.
Your job is to find every reason NOT to take a trade. You only approve trades that survive rigorous scrutiny.
List risks first, then your decision.

When evaluating a trade signal, respond with valid JSON:
{
  "decision": "APPROVE" | "REJECT" | "MODIFY",
  "reasoning": "clear explanation of your decision",
  "risk_score": 1-10,
  "risks_identified": ["risk 1", "risk 2"],
  "modified_params": null or {"stop_loss": x, "take_profit": y, "max_leverage": z}
}

Be conservative. A 6/10 risk score should give you pause. 8+ should almost always be rejected."""


class GuardianAgent(BaseAgent):
    agent_id = AgentID.GUARDIAN
    display_name = "Guardian"
    model_env_key = "agent_guardian_model"
    personality = PERSONALITY

    def __init__(self, settings):
        super().__init__(settings)
        # Signals held here until Commander issues PIPELINE_DECISION
        self._pending_signals: dict[str, dict] = {}

    async def _run_loop(self) -> None:
        # Guardian is event-driven — no scheduled loop needed
        while True:
            await asyncio.sleep(60)
            await self.emit_status("Monitoring for signals")

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.MARKET_SIGNAL:
            # Store signal keyed by signal_id; wait for Commander's decision
            signal_id = msg.payload.get("signal_id")
            if signal_id:
                self._pending_signals[signal_id] = {"payload": msg.payload, "msg_id": msg.id}
        elif msg.message_type == MessageType.PIPELINE_DECISION:
            decision = msg.payload.get("decision")
            signal_id = msg.payload.get("signal_id")
            if decision == "advance" and signal_id in self._pending_signals:
                pending = self._pending_signals.pop(signal_id)
                await self._evaluate_signal(pending["payload"], pending["msg_id"])
            elif signal_id:
                # Blocked or expired — discard
                self._pending_signals.pop(signal_id, None)
        elif msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.GUARDIAN:
            await self._on_chat(msg)

    async def _evaluate_signal(self, signal: dict, correlation_id: str) -> None:
        pair = signal.get("pair", "")
        await self.emit_status(f"Evaluating {pair} {signal.get('direction')} signal")

        # Step 1: Hard rule validators (no LLM)
        hard_result = await validate_hard_rules(signal, self.settings)
        if not hard_result.passed:
            await self._reject(signal, hard_result.reason, risk_score=1)
            return

        # Step 2: LLM critique
        ctx = await self.build_shared_context()
        sage_insights = ctx.get("sage_insights", {})

        # Fetch recent trade performance for context
        async with get_session() as sess:
            perf = await sess.execute(text("""
                SELECT pair, COUNT(*) as trades,
                       ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl_pct
                FROM trades WHERE status = 'closed' AND closed_at >= now() - interval '7 days'
                GROUP BY pair ORDER BY avg_pnl_pct DESC
            """))
            recent_perf = [dict(r._mapping) for r in perf.fetchall()]

        prompt = f"""Evaluate this trade signal for approval:

## Signal
{json.dumps(signal, indent=2)}

## Portfolio Context
Open positions: {len(ctx.get('open_positions', []))} / 3
Portfolio: {json.dumps(ctx.get('portfolio', {}), indent=2)}

## Recent Performance (7 days)
{json.dumps(recent_perf, indent=2)}

## Learning Insights from Sage
{json.dumps(sage_insights, indent=2)}

Apply devil's advocate reasoning. What could go wrong? Is the risk/reward justified?
Respond in JSON as specified in your system prompt."""

        result = await self.think_json([{"role": "user", "content": prompt}])
        decision = result.get("decision", "REJECT").upper()

        # Persist Guardian's notes on the signal
        async with get_session() as sess:
            await sess.execute(text("""
                UPDATE signals
                SET status = :status, guardian_notes = :notes, modified_params = CAST(:mods AS jsonb)
                WHERE id = :id
            """), {
                "status": "approved" if decision == "APPROVE" else
                          "modified" if decision == "MODIFY" else "rejected",
                "notes": result.get("reasoning", ""),
                "mods": json.dumps(result.get("modified_params")),
                "id": signal.get("signal_id"),
            })
            await sess.commit()

        if decision in ("APPROVE", "MODIFY"):
            final_signal = {**signal, **(result.get("modified_params") or {})}
            await self.publish(AtlasMessage(
                source_agent=AgentID.GUARDIAN,
                message_type=MessageType.TRADE_APPROVED if decision == "APPROVE" else MessageType.TRADE_MODIFIED,
                payload={
                    **final_signal,
                    "guardian_reasoning": result.get("reasoning"),
                    "risk_score": result.get("risk_score", 5),
                },
                correlation_id=correlation_id,
                priority=4,
            ))
            logger.info("[Guardian] %s: %s %s (risk %d/10)",
                        decision, pair, signal.get("direction"), result.get("risk_score", 5))
        else:
            await self._reject(signal, result.get("reasoning", "Rejected by Guardian"),
                               risk_score=result.get("risk_score", 8))


    async def _reject(self, signal: dict, reason: str, risk_score: int = 8) -> None:
        async with get_session() as sess:
            await sess.execute(text("""
                UPDATE signals SET status = 'rejected', guardian_notes = :notes
                WHERE id = :id
            """), {"notes": reason, "id": signal.get("signal_id")})
            await sess.commit()

        await self.publish(AtlasMessage(
            source_agent=AgentID.GUARDIAN,
            message_type=MessageType.TRADE_REJECTED,
            payload={
                "signal_id": signal.get("signal_id"),
                "pair": signal.get("pair"),
                "reason": reason,
                "risk_score": risk_score,
            },
        ))
        logger.info("[Guardian] REJECTED %s: %s", signal.get("pair"), reason)

    async def _on_chat(self, msg: AtlasMessage) -> None:
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}]
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.GUARDIAN,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    agent = GuardianAgent(get_settings())
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
