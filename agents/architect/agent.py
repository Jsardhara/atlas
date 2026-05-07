"""Architect — Strategy ranking + chat agent.

Note (2026-05-07): the Freqtrade strategy-codegen + backtest path was
removed when Freqtrade itself was dropped. Architect now lives as a
heartbeat-only agent in the message bus, plus chat handler. Strategy
selection happens via the bull/bear debate in Oracle (see
``oracle/data_sources/debate.py``); strategy weight overrides come from
``/control/strategy-weights`` (Redis ``atlas:strategy_weights``).
"""
import asyncio
import logging

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.protocols import AgentID, AtlasMessage, MessageType

logger = logging.getLogger(__name__)

GENERATION_INTERVAL = 7 * 24 * 3600  # Weekly heartbeat (legacy cadence)

PERSONALITY = """You are Architect, a quantitative strategist for ATLAS.
You speak in structured, numbered points. You comment on signal quality,
regime fit, and rank-weighting for the bull/bear debate output produced
by Oracle. You do NOT write Freqtrade strategy code (that path is
deprecated). You answer operator questions about strategy weighting,
universe selection, and how the debate is converging."""


class ArchitectAgent(BaseAgent):
    agent_id = AgentID.ARCHITECT
    display_name = "Architect"
    model_env_key = "agent_architect_model"
    personality = PERSONALITY

    async def _run_loop(self) -> None:
        # Heartbeat-only run loop. Strategy generation lived here when
        # Freqtrade was the execution engine; that path was retired with
        # PR ``chore/drop-freqtrade``. The agent now exists for chat +
        # message-bus presence; ranking/weights happen in Oracle.debate
        # and via /control/strategy-weights.
        while True:
            await asyncio.sleep(GENERATION_INTERVAL)

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.ARCHITECT:
            await self._on_chat(msg)

    async def _on_chat(self, msg: AtlasMessage) -> None:
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}]
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.ARCHITECT,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    agent = ArchitectAgent(get_settings())
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
