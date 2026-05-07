"""Abstract BaseAgent — all 6 agents extend this."""
import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

from sqlalchemy import text

from .config import Settings
from .db import get_session, init_db
from .message_bus import MessageBus
from .claude_client import ClaudeClient
from .protocols import AgentID, AgentState, AtlasMessage, MessageType

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    agent_id: AgentID
    display_name: str
    personality: str        # System prompt persona
    model_env_key: str      # e.g. "agent_oracle_model"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = AgentState.STARTING
        self.model = getattr(settings, self.model_env_key)
        self.bus = MessageBus(settings.redis_url)
        self.llm = ClaudeClient(
            model=self.model,
            agent_id=self.agent_id.value,
        )
        self._start_time = time.time()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    async def start(self) -> None:
        init_db(self.settings.database_url)
        await self.bus.connect()
        self.state = AgentState.RUNNING
        await self._update_db_state(AgentState.RUNNING)
        logger.info("[%s] Started with model %s", self.display_name, self.model)

        await asyncio.gather(
            self._heartbeat_loop(),
            self._consume_loop(),
            self._run_loop(),
        )

    async def _heartbeat_loop(self) -> None:
        while self.state != AgentState.ERROR:
            await self.publish(AtlasMessage(
                source_agent=self.agent_id,
                message_type=MessageType.HEARTBEAT,
                payload={"state": self.state.value, "uptime": int(time.time() - self._start_time)},
            ))
            await self._update_heartbeat()
            await asyncio.sleep(30)

    async def _consume_loop(self) -> None:
        await self.bus.consume(self.agent_id, self._handle_message)

    # -------------------------------------------------------------------------
    # Override in subclasses
    # -------------------------------------------------------------------------
    @abstractmethod
    async def _run_loop(self) -> None:
        """Main agent work loop — scheduled tasks, polling, etc."""

    @abstractmethod
    async def process_message(self, msg: AtlasMessage) -> None:
        """Handle an incoming bus message."""

    # -------------------------------------------------------------------------
    # Shared helpers
    # -------------------------------------------------------------------------
    async def _handle_message(self, msg: AtlasMessage) -> None:
        if self.state == AgentState.PAUSED and msg.message_type != MessageType.AGENT_COMMAND:
            return
        try:
            await self.process_message(msg)
        except Exception as e:
            logger.error("[%s] Error processing %s: %s", self.display_name, msg.message_type, e)

    async def publish(self, msg: AtlasMessage) -> None:
        try:
            await self.bus.publish(msg)
        except Exception as e:
            logger.error("[%s] Failed to publish %s: %s", self.display_name, msg.message_type, e)

    async def emit_status(self, activity: str) -> None:
        await self.publish(AtlasMessage(
            source_agent=self.agent_id,
            message_type=MessageType.AGENT_STATUS,
            payload={"activity": activity, "state": self.state.value},
        ))

    async def think(
        self,
        messages: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        return await self.llm.chat(messages, system=system or self.personality,
                                   temperature=temperature, max_tokens=max_tokens)

    async def think_json(self, messages: list[dict], system: str | None = None) -> dict:
        raw = await self.llm.chat(
            messages,
            system=system or self.personality,
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

    async def save_memory(self, key: str, value: dict) -> None:
        async with get_session() as sess:
            await sess.execute(text("""
                INSERT INTO agent_memory (agent_id, memory_key, value, updated_at)
                VALUES (:agent, :key, CAST(:val AS jsonb), now())
                ON CONFLICT (agent_id, memory_key)
                DO UPDATE SET value = CAST(:val AS jsonb), updated_at = now()
            """), {"agent": self.agent_id.value, "key": key, "val": json.dumps(value)})
            await sess.commit()

    async def load_memory(self, key: str) -> dict | None:
        async with get_session() as sess:
            row = await sess.execute(text("""
                SELECT value FROM agent_memory WHERE agent_id = :agent AND memory_key = :key
            """), {"agent": self.agent_id.value, "key": key})
            result = row.fetchone()
            return result[0] if result else None

    async def build_shared_context(self) -> dict:
        """Load common context injected into every agent's prompts."""
        async with get_session() as sess:
            # Open positions
            positions = await sess.execute(text(
                "SELECT pair, side, leverage, entry_price, pnl_pct FROM trades WHERE status = 'open'"
            ))
            open_trades = [dict(r._mapping) for r in positions.fetchall()]

            # Latest portfolio snapshot
            snap = await sess.execute(text(
                "SELECT total_usd, available_usd, realized_pnl, unrealized_pnl "
                "FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
            ))
            snap_row = snap.fetchone()
            portfolio = dict(snap_row._mapping) if snap_row else {}

            # Sage insights
            sage_memory = await self.load_memory("latest_insights")

        return {
            "open_positions": open_trades,
            "portfolio": portfolio,
            "sage_insights": sage_memory or {},
            "live_trading_enabled": self.settings.live_trading_enabled,
        }

    async def _update_db_state(self, state: AgentState) -> None:
        try:
            async with get_session() as sess:
                await sess.execute(text(
                    "UPDATE agents SET state = :state WHERE id = :id"
                ), {"state": state.value, "id": self.agent_id.value})
                await sess.commit()
        except Exception as e:
            logger.warning("[%s] Could not update DB state: %s", self.display_name, e)

    async def _update_heartbeat(self) -> None:
        try:
            async with get_session() as sess:
                await sess.execute(text(
                    "UPDATE agents SET last_heartbeat = now() WHERE id = :id"
                ), {"id": self.agent_id.value})
                await sess.commit()
        except Exception:
            pass
