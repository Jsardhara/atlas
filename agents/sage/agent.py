"""Sage — Learning and pattern analysis agent."""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import AgentID, AtlasMessage, MessageType

logger = logging.getLogger(__name__)

PERSONALITY = """You are Sage, a philosophical and methodical performance analyst.
You look for deep patterns in trading history, not just surface statistics.
You speak in measured paragraphs, not bullet points. You question whether past patterns will persist.
You provide actionable insights to help Oracle identify better signals and Guardian calibrate risk.

When analyzing trades, respond with valid JSON:
{
  "key_insights": ["insight 1", "insight 2", "insight 3"],
  "best_conditions": "description of when trades worked well",
  "worst_conditions": "description of when trades failed",
  "pair_performance": {"BTC/USD": {"bias": "LONG", "avg_pnl_pct": 0.02}, ...},
  "time_patterns": "any time-of-day or day-of-week patterns observed",
  "recommendations": ["recommendation for Oracle", "recommendation for Guardian"],
  "regime_assessment": "current market regime assessment based on recent trades"
}"""

ANALYSIS_INTERVAL = 6 * 3600  # 6 hours
TRIGGER_TRADE_COUNT = 10       # Also trigger after every 10 closed trades


class SageAgent(BaseAgent):
    agent_id = AgentID.SAGE
    display_name = "Sage"
    model_env_key = "agent_sage_model"
    personality = PERSONALITY

    def __init__(self, settings):
        super().__init__(settings)
        self._trades_since_analysis = 0

    async def _run_loop(self) -> None:
        await asyncio.sleep(120)  # Let trades accumulate
        while True:
            await self._analysis_cycle()
            await asyncio.sleep(ANALYSIS_INTERVAL)

    async def _analysis_cycle(self) -> None:
        await self.emit_status("Running trade analysis")

        async with get_session() as sess:
            # Fetch recent closed trades
            result = await sess.execute(text("""
                SELECT pair, side, leverage, entry_price, exit_price,
                       pnl_usd, pnl_pct, opened_at, closed_at, close_reason,
                       EXTRACT(hour FROM opened_at) as open_hour,
                       EXTRACT(dow FROM opened_at) as open_dow
                FROM trades
                WHERE status = 'closed'
                ORDER BY closed_at DESC
                LIMIT 100
            """))
            trades = [dict(r._mapping) for r in result.fetchall()]

            if len(trades) < 5:
                await self.emit_status("Not enough trades yet for analysis (need 5+)")
                return

            # Aggregate stats
            stats = await sess.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                    ROUND(AVG(pnl_pct)::numeric, 4) as avg_pnl_pct,
                    ROUND(SUM(pnl_usd)::numeric, 2) as total_pnl_usd,
                    ROUND(MAX(pnl_usd)::numeric, 2) as best_usd,
                    ROUND(MIN(pnl_usd)::numeric, 2) as worst_usd,
                    ROUND(AVG(EXTRACT(epoch FROM (closed_at - opened_at))/3600)::numeric, 2) as avg_hold_hours
                FROM trades WHERE status = 'closed'
            """))
            agg = dict(stats.fetchone()._mapping)

        # Serialize for JSON (handle Decimal/datetime/text columns).
        # Only cast to float when the value is actually numeric — text
        # columns like pair/side/status/order_type stay strings.
        def _as_jsonable(v):
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            if isinstance(v, (int, float)):
                return v
            try:
                return float(v)
            except (TypeError, ValueError):
                return str(v)

        trades_json = []
        for t in trades[:50]:  # Limit context size
            trades_json.append({k: _as_jsonable(v) for k, v in t.items()})

        prompt = f"""Analyze these {len(trades)} recent trades and provide deep learning insights.

## Aggregate Statistics
{json.dumps({k: _as_jsonable(v) for k, v in agg.items()}, indent=2, default=str)}

## Individual Trades (most recent 50)
{json.dumps(trades_json, indent=2)}

Identify patterns, conditions for success/failure, and specific recommendations for:
1. Oracle: Which pairs/conditions produce better signals?
2. Guardian: What risk thresholds should be adjusted?
3. Overall: What is the market regime telling us?

Respond in JSON as specified in your system prompt."""

        insights = await self.think_json([{"role": "user", "content": prompt}])

        # Persist insights for other agents to read
        await self.save_memory("latest_insights", {
            **insights,
            "trade_count": len(trades),
            "stats": {k: _as_jsonable(v) for k, v in agg.items()},
            "analyzed_at": datetime.utcnow().isoformat(),
        })

        # Update paper trading readiness stats
        total = agg.get("total", 0) or 0
        wins = agg.get("wins", 0) or 0
        win_rate = wins / max(total, 1)

        # Calculate max drawdown
        equity = 1000.0
        peak = equity
        max_dd = 0.0
        for t in reversed(trades):
            pnl = float(t.get("pnl_usd") or 0)
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        async with get_session() as sess:
            await sess.execute(text("""
                UPDATE paper_trading_stats SET
                    total_trades = :total,
                    win_rate_30 = :wr,
                    max_drawdown_pct = :dd,
                    updated_at = now()
            """), {"total": int(total), "wr": round(win_rate, 4), "dd": round(max_dd, 4)})
            await sess.commit()

        await self.publish(AtlasMessage(
            source_agent=AgentID.SAGE,
            message_type=MessageType.LEARNING_INSIGHT,
            payload=insights,
            priority=3,
        ))
        await self.publish(AtlasMessage(
            source_agent=AgentID.SAGE,
            message_type=MessageType.PERFORMANCE_REPORT,
            payload={**agg, "win_rate": round(win_rate, 4), "max_drawdown": round(max_dd, 4)},
        ))
        logger.info("[Sage] Analysis complete: %d trades, win_rate=%.1f%%", total, win_rate * 100)
        self._trades_since_analysis = 0

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.POSITION_CLOSED:
            self._trades_since_analysis += 1
            if self._trades_since_analysis >= TRIGGER_TRADE_COUNT:
                asyncio.create_task(self._analysis_cycle())
        elif msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.SAGE:
            await self._on_chat(msg)

    async def _on_chat(self, msg: AtlasMessage) -> None:
        memory = await self.load_memory("latest_insights")
        context = f"\n\nLatest insights: {json.dumps(memory, indent=2)}" if memory else ""
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}],
            system=PERSONALITY + context,
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.SAGE,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    agent = SageAgent(get_settings())
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
