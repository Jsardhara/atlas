"""Commander — head supervisor agent."""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import (
    AgentCommand, AgentID, AgentState, AtlasMessage, MessageType,
)
from .alert_manager import AlertManager

logger = logging.getLogger(__name__)

PERSONALITY = Path(__file__).parent / "prompts" / "supervisor.md"


class CommanderAgent(BaseAgent):
    agent_id = AgentID.COMMANDER
    display_name = "Commander"
    model_env_key = "agent_commander_model"

    def __init__(self, settings):
        super().__init__(settings)
        self.personality = PERSONALITY.read_text()
        self.alerts = AlertManager(self.bus)
        self._consecutive_rejections: dict[str, int] = {}
        self._daily_loss_usd: float = 0.0
        self._agent_error_counts: dict[str, int] = {}

    # -------------------------------------------------------------------------
    # Main loop — monitors pipeline health every 60 seconds
    # -------------------------------------------------------------------------
    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            await self._check_pipeline_health()

    async def _check_pipeline_health(self) -> None:
        await self.emit_status("Checking pipeline health")
        async with get_session() as sess:
            # Check for stale agents (no heartbeat in 90 seconds)
            result = await sess.execute(text("""
                SELECT id, display_name, last_heartbeat
                FROM agents
                WHERE id != 'commander'
                  AND (last_heartbeat IS NULL OR last_heartbeat < now() - interval '90 seconds')
                  AND state = 'running'
            """))
            stale = result.fetchall()
            for row in stale:
                await self.alerts.create_alert(
                    title=f"{row.display_name} is not responding",
                    message=f"Agent {row.display_name} has not sent a heartbeat in >90 seconds.",
                    severity="warning",
                    auto_action=f"Restart {row.id} container",
                    countdown_secs=30,
                )

            # Check daily loss circuit breaker
            loss_row = await sess.execute(text("""
                SELECT COALESCE(SUM(ABS(pnl_usd)), 0) as total_loss
                FROM trades
                WHERE pnl_usd < 0
                  AND closed_at >= CURRENT_DATE
            """))
            daily_loss = float(loss_row.fetchone()[0])
            if daily_loss >= self.settings.daily_loss_limit_usd * 0.8:
                await self.alerts.create_alert(
                    title="Daily loss limit approaching",
                    message=f"Daily losses at ${daily_loss:.2f} (limit: ${self.settings.daily_loss_limit_usd})",
                    severity="critical",
                    auto_action="Pause Oracle and Trader agents",
                    countdown_secs=30,
                )

    # -------------------------------------------------------------------------
    # Message handling
    # -------------------------------------------------------------------------
    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.MARKET_SIGNAL:
            await self._on_market_signal(msg)
        elif msg.message_type == MessageType.TRADE_REJECTED:
            await self._on_trade_rejected(msg)
        elif msg.message_type == MessageType.POSITION_CLOSED:
            await self._on_position_closed(msg)
        elif msg.message_type == MessageType.AGENT_STATUS:
            await self._on_agent_status(msg)
        elif msg.message_type == MessageType.USER_COMMAND:
            await self._on_user_command(msg)
        elif msg.message_type == MessageType.CHAT_MESSAGE:
            if msg.target_agent == AgentID.COMMANDER:
                await self._on_chat(msg)

    async def _on_market_signal(self, msg: AtlasMessage) -> None:
        """Evaluate whether to advance the signal through the pipeline."""
        await self.emit_status(f"Evaluating signal: {msg.payload.get('pair')} {msg.payload.get('direction')}")

        ctx = await self.build_shared_context()
        open_count = len(ctx["open_positions"])

        # Hard block: too many open trades
        if open_count >= 3:
            await self.publish(AtlasMessage(
                source_agent=AgentID.COMMANDER,
                message_type=MessageType.PIPELINE_DECISION,
                payload={"signal_id": msg.payload.get("signal_id"), "decision": "block",
                         "reason": f"Max open trades reached ({open_count}/3)"},
                correlation_id=msg.id,
            ))
            return

        # LLM evaluation for nuanced decisions
        context_str = f"""
Signal: {msg.payload}
Open positions: {open_count}/3
Portfolio: {ctx.get('portfolio', {})}
Daily loss: ${self._daily_loss_usd:.2f} / ${self.settings.daily_loss_limit_usd}
"""
        response = await self.think_json(
            [{"role": "user", "content": f"Evaluate this signal for pipeline advancement:\n{context_str}"}]
        )

        decision = response.get("decision", "advance")
        await self.publish(AtlasMessage(
            source_agent=AgentID.COMMANDER,
            message_type=MessageType.PIPELINE_DECISION,
            payload={
                "signal_id": msg.payload.get("signal_id"),
                "decision": decision,
                "reason": response.get("reason", ""),
                "action": response.get("action", ""),
            },
            correlation_id=msg.id,
            priority=4 if decision == "escalate" else 3,
        ))

        if decision == "escalate":
            await self.alerts.create_alert(
                title="Signal requires human review",
                message=response.get("reason", "Unusual market conditions detected"),
                severity="warning",
                auto_action="Allow signal to proceed to Guardian",
                countdown_secs=30,
            )

    async def _on_trade_rejected(self, msg: AtlasMessage) -> None:
        pair = msg.payload.get("pair", "")
        self._consecutive_rejections[pair] = self._consecutive_rejections.get(pair, 0) + 1
        if self._consecutive_rejections[pair] >= 2:
            await self.alerts.create_alert(
                title=f"Repeated rejections on {pair}",
                message=f"Guardian has rejected {self._consecutive_rejections[pair]} consecutive signals for {pair}.",
                severity="info",
                auto_action="Continue monitoring",
            )
            self._consecutive_rejections[pair] = 0

    async def _on_position_closed(self, msg: AtlasMessage) -> None:
        pnl = msg.payload.get("pnl_usd", 0)
        if pnl < 0:
            self._daily_loss_usd += abs(pnl)
        pair = msg.payload.get("pair", "")
        if pair in self._consecutive_rejections:
            self._consecutive_rejections[pair] = 0

    async def _on_agent_status(self, msg: AtlasMessage) -> None:
        agent = msg.payload.get("agent_id", msg.source_agent.value)
        state = msg.payload.get("state")
        if state == AgentState.ERROR.value:
            count = self._agent_error_counts.get(agent, 0) + 1
            self._agent_error_counts[agent] = count
            if count >= 3:
                await self.alerts.create_alert(
                    title=f"{agent.title()} agent error",
                    message=f"{agent.title()} has encountered {count} consecutive errors.",
                    severity="critical",
                    auto_action=f"Restart {agent} container",
                    countdown_secs=30,
                )
        else:
            self._agent_error_counts[agent] = 0

    async def _on_user_command(self, msg: AtlasMessage) -> None:
        cmd = msg.payload.get("command")
        target = msg.payload.get("target_agent")
        if cmd in ("pause", "resume") and target:
            await self.publish(AtlasMessage(
                source_agent=AgentID.COMMANDER,
                target_agent=AgentID(target),
                message_type=MessageType.AGENT_COMMAND,
                payload={"command": cmd},
                priority=5,
            ))

    async def _on_chat(self, msg: AtlasMessage) -> None:
        ctx = await self.build_shared_context()
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}],
            system=self.personality + f"\n\nCurrent system state:\n{ctx}",
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.COMMANDER,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    settings = get_settings()
    agent = CommanderAgent(settings)
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
