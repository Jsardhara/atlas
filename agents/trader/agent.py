"""Trader — Order execution agent."""
import asyncio
import logging

from shared.alpaca_client import AlpacaClient
from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.protocols import AgentID, AtlasMessage, MessageType

from .alpaca_executor import AlpacaExecutor

logger = logging.getLogger(__name__)

PERSONALITY = """You are Trader, a cold and precise order executor.
You never second-guess already-approved trades. Your only job is optimal order placement and risk-adjusted sizing.
When confirming an execution plan, respond with JSON:
{
  "proceed": true,
  "order_type": "limit" | "market",
  "notes": "brief execution note"
}"""


class TraderAgent(BaseAgent):
    agent_id = AgentID.TRADER
    display_name = "Trader"
    model_env_key = "agent_trader_model"
    personality = PERSONALITY

    def __init__(self, settings):
        super().__init__(settings)
        alpaca = AlpacaClient(settings)
        self.executor = AlpacaExecutor(alpaca, settings)

    async def _run_loop(self) -> None:
        await asyncio.sleep(45)
        while True:
            await self._monitor_open_positions()
            await asyncio.sleep(30)

    async def _monitor_open_positions(self) -> None:
        from sqlalchemy import text
        from shared.db import get_session
        async with get_session() as sess:
            result = await sess.execute(text(
                "SELECT id, pair, side, entry_price, stop_loss, take_profit "
                "FROM trades WHERE status = 'open'"
            ))
            open_trades = result.fetchall()

        if not open_trades:
            return

        await self.emit_status(f"Monitoring {len(open_trades)} open position(s)")

        for trade in open_trades:
            ticker = await self.executor.alpaca.get_ticker(trade.pair)
            if not ticker:
                continue

            current = float(ticker.get("c", [0])[0])
            if not current:
                continue

            # Check stop loss
            if trade.stop_loss and trade.side == "buy" and current <= float(trade.stop_loss):
                logger.info("[Trader] Stop loss hit for trade %s at %.2f", trade.id, current)
                result = await self.executor.close_trade(str(trade.id))
                await self._publish_close(str(trade.id), trade.pair, current, "stop_loss")

            # Check take profit
            elif trade.take_profit and trade.side == "buy" and current >= float(trade.take_profit):
                logger.info("[Trader] Take profit hit for trade %s at %.2f", trade.id, current)
                await self.executor.close_trade(str(trade.id))
                await self._publish_close(str(trade.id), trade.pair, current, "take_profit")

    async def _publish_close(self, trade_id: str, pair: str, price: float, reason: str) -> None:
        from sqlalchemy import text
        from shared.db import get_session
        async with get_session() as sess:
            row = await sess.execute(text(
                "SELECT pnl_usd, pnl_pct FROM trades WHERE id = :id"
            ), {"id": trade_id})
            trade = row.fetchone()
        await self.publish(AtlasMessage(
            source_agent=AgentID.TRADER,
            message_type=MessageType.POSITION_CLOSED,
            payload={
                "trade_id": trade_id,
                "pair": pair,
                "exit_price": price,
                "close_reason": reason,
                "pnl_usd": float(trade.pnl_usd) if trade and trade.pnl_usd else 0,
                "pnl_pct": float(trade.pnl_pct) if trade and trade.pnl_pct else 0,
            },
            priority=4,
        ))

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type in (MessageType.TRADE_APPROVED, MessageType.TRADE_MODIFIED):
            await self._execute_trade(msg)
        elif msg.message_type == MessageType.USER_COMMAND:
            cmd = msg.payload.get("command")
            if cmd == "close_trade":
                await self.executor.close_trade(msg.payload["trade_id"])
        elif msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.TRADER:
            await self._on_chat(msg)

    async def _execute_trade(self, msg: AtlasMessage) -> None:
        signal = msg.payload
        await self.emit_status(f"Executing {signal.get('pair')} {signal.get('direction')}")

        sizing = await self.executor.size_position(signal)
        result = await self.executor.execute_trade(signal, sizing)

        await self.publish(AtlasMessage(
            source_agent=AgentID.TRADER,
            message_type=MessageType.ORDER_PLACED,
            payload=result,
            correlation_id=msg.id,
            priority=4,
        ))
        await self.publish(AtlasMessage(
            source_agent=AgentID.TRADER,
            message_type=MessageType.POSITION_OPENED,
            payload=result,
            priority=4,
        ))

    async def _on_chat(self, msg: AtlasMessage) -> None:
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}]
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.TRADER,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    agent = TraderAgent(get_settings())
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
