"""Architect — Strategy generation and backtesting agent."""
import asyncio
import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import AgentID, AtlasMessage, MessageType

from .backtest_runner import run_backtest, score_backtest

logger = logging.getLogger(__name__)

STRATEGIES_PATH = Path("/freqtrade/user_data/strategies")
GENERATION_INTERVAL = 7 * 24 * 3600  # Weekly

PERSONALITY = """You are Architect, a creative but rigorous cryptocurrency strategy designer.
You draw on quantitative finance, market microstructure, and academic research.
You write complete, working Freqtrade strategies in Python.

When generating a strategy, you MUST produce a complete Python class that:
1. Extends IStrategy
2. Implements populate_indicators(), populate_entry_trend(), populate_exit_trend()
3. Uses only standard ta-lib / pandas-ta / numpy indicators
4. Has clear ROI table, stoploss, and timeframe set
5. Includes sensible hyperparameter ranges

Return JSON:
{
  "strategy_name": "UniqueStrategyName",
  "rationale": "Why this strategy should work",
  "market_regime": "Bull/Bear/Any",
  "code": "complete Python source code as a string"
}"""


class ArchitectAgent(BaseAgent):
    agent_id = AgentID.ARCHITECT
    display_name = "Architect"
    model_env_key = "agent_architect_model"
    personality = PERSONALITY

    async def _run_loop(self) -> None:
        await asyncio.sleep(300)  # Wait for system to stabilize
        while True:
            try:
                await self._generation_cycle()
            except Exception as e:
                logger.error("[Architect] Generation cycle error: %s", e)
            await asyncio.sleep(GENERATION_INTERVAL)

    async def _generation_cycle(self) -> None:
        await self.emit_status("Designing new strategy")

        # Load Sage insights for context
        sage_insights = await self.load_memory("latest_insights") or {}

        # Load existing strategy names to avoid duplicates
        async with get_session() as sess:
            result = await sess.execute(text("SELECT name FROM strategies ORDER BY created_at DESC LIMIT 5"))
            existing = [r[0] for r in result.fetchall()]

        prompt = f"""Design a new cryptocurrency trading strategy based on recent market insights.

## Sage Learning Insights
{json.dumps(sage_insights, indent=2)}

## Existing Strategies (avoid duplicate approaches)
{existing}

## Requirements
- Target broker: Alpaca (US equities — top liquid tickers from screener output)
- Must work for both long and short (margin-eligible symbols only)
- Timeframe: 5m or 15m preferred
- Should exploit patterns identified in the insights above
- Use a DIFFERENT approach from existing strategies

Generate a complete, production-ready Freqtrade strategy. Respond in JSON."""

        result = await self.think_json([{"role": "user", "content": prompt}])

        strategy_name = result.get("strategy_name", f"AtlasStrategy_{uuid.uuid4().hex[:6]}")
        code = result.get("code", "")

        if not code or "class " not in code:
            logger.warning("[Architect] Invalid strategy code generated")
            return

        # Write strategy file
        STRATEGIES_PATH.mkdir(parents=True, exist_ok=True)
        strategy_file = STRATEGIES_PATH / f"{strategy_name}.py"
        strategy_file.write_text(code)
        logger.info("[Architect] Strategy written: %s", strategy_file)

        # Save to DB as proposed
        async with get_session() as sess:
            row = await sess.execute(text("""
                INSERT INTO strategies (name, code, status, proposed_by)
                VALUES (:name, :code, 'proposed', 'architect')
                ON CONFLICT (name) DO UPDATE SET code = :code, version = strategies.version + 1
                RETURNING id
            """), {"name": strategy_name, "code": code})
            strategy_id = str(row.fetchone()[0])
            await sess.commit()

        await self.publish(AtlasMessage(
            source_agent=AgentID.ARCHITECT,
            message_type=MessageType.STRATEGY_PROPOSED,
            payload={
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "rationale": result.get("rationale", ""),
                "market_regime": result.get("market_regime", "Any"),
            },
        ))

        # Run backtest
        await self.emit_status(f"Backtesting {strategy_name}")
        await self.publish(AtlasMessage(
            source_agent=AgentID.ARCHITECT,
            message_type=MessageType.BACKTEST_STARTED,
            payload={"strategy_id": strategy_id, "strategy_name": strategy_name},
        ))

        async with get_session() as sess:
            bt_row = await sess.execute(text("""
                INSERT INTO backtests (strategy_id, triggered_by, timerange, status)
                VALUES (:sid::uuid, 'architect', '20240101-', 'running')
                RETURNING id
            """), {"sid": strategy_id})
            backtest_id = str(bt_row.fetchone()[0])
            await sess.commit()

        bt_results = await run_backtest(strategy_name)
        metrics = score_backtest(bt_results)

        async with get_session() as sess:
            await sess.execute(text("""
                UPDATE backtests SET
                    status = :status, results = CAST(:res AS jsonb),
                    sharpe_ratio = :sharpe, max_drawdown = :dd,
                    total_return = :ret, win_rate = :wr,
                    completed_at = now()
                WHERE id = :id
            """), {
                "status": "failed" if "error" in metrics else "completed",
                "res": json.dumps(bt_results),
                "sharpe": metrics.get("sharpe_ratio", 0),
                "dd": metrics.get("max_drawdown", 0),
                "ret": metrics.get("profit_total_pct", 0),
                "wr": metrics.get("win_rate", 0),
                "id": backtest_id,
            })
            await sess.execute(text("""
                UPDATE strategies SET backtest_results = CAST(:res AS jsonb),
                    performance_metrics = CAST(:metrics AS jsonb), status = 'testing'
                WHERE id = :id
            """), {"res": json.dumps(bt_results), "metrics": json.dumps(metrics), "id": strategy_id})
            await sess.commit()

        await self.publish(AtlasMessage(
            source_agent=AgentID.ARCHITECT,
            message_type=MessageType.BACKTEST_COMPLETE,
            payload={
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "backtest_id": backtest_id,
                "metrics": metrics,
            },
            priority=4,
        ))
        logger.info("[Architect] Backtest complete for %s: %s", strategy_name, metrics)

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.USER_COMMAND:
            if msg.payload.get("command") == "generate_strategy":
                asyncio.create_task(self._generation_cycle())
        elif msg.message_type == MessageType.PERFORMANCE_REPORT:
            win_rate = msg.payload.get("win_rate", 1.0)
            if float(win_rate) < 0.45:
                logger.info("[Architect] Low win rate (%.1f%%) — triggering strategy generation", win_rate * 100)
                asyncio.create_task(self._generation_cycle())
        elif msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.ARCHITECT:
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
