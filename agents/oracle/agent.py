"""Oracle — Research and signal generation agent."""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import AgentID, AtlasMessage, MarketSignal, MessageType

from .data_sources.freqtrade import FreqtradeClient
from .data_sources.news import fetch_cryptopanic, fetch_fear_and_greed, fetch_rss_headlines

logger = logging.getLogger(__name__)

PERSONALITY = """You are Oracle, a sharp and unemotional crypto market analyst.
You speak in structured, numbered points. You never hedge with 'maybe' — you give a confidence score instead.
You consider macro conditions, news sentiment, fear/greed index, and technical signals together.
Your goal is generating actionable trading signals with clear reasoning.

When asked to generate signals, respond with valid JSON:
{
  "signals": [
    {
      "pair": "BTC/USD",
      "direction": "LONG",
      "confidence": 0.72,
      "reasoning": "...",
      "entry_price": 65000,
      "stop_loss": 62000,
      "take_profit": 71000,
      "sources": ["fear_greed: 35 (Fear)", "news: BTC ETF inflows rising"]
    }
  ],
  "market_summary": "Brief overall market assessment",
  "regime": "BULL | BEAR | SIDEWAYS | CHOPPY"
}
Only include signals with confidence >= 0.6."""

TRADING_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"]
SCAN_INTERVAL = 900  # 15 minutes


class OracleAgent(BaseAgent):
    agent_id = AgentID.ORACLE
    display_name = "Oracle"
    model_env_key = "agent_oracle_model"
    personality = PERSONALITY

    def __init__(self, settings):
        super().__init__(settings)
        self.freqtrade = FreqtradeClient(
            settings.freqtrade_url,
            settings.freqtrade_username,
            settings.freqtrade_password,
        )

    async def _run_loop(self) -> None:
        await asyncio.sleep(30)  # Let other services start
        while True:
            try:
                await self._research_cycle()
            except Exception as e:
                logger.error("[Oracle] Research cycle error: %s", e)
            await asyncio.sleep(SCAN_INTERVAL)

    async def _research_cycle(self) -> None:
        await self.emit_status("Starting research cycle")

        # Fetch all data sources concurrently
        await self.emit_status("Fetching market data")
        news, rss, fng, ft_status, ft_perf, ctx = await asyncio.gather(
            fetch_cryptopanic(self.settings.cryptopanic_api_key, TRADING_PAIRS),
            fetch_rss_headlines(),
            fetch_fear_and_greed(),
            self.freqtrade.get_status(),
            self.freqtrade.get_performance(),
            self.build_shared_context(),
        )

        await self.emit_status("Analyzing market conditions")

        sage_insights = ctx.get("sage_insights", {})
        open_pairs = [p["pair"] for p in ctx.get("open_positions", [])]

        prompt = f"""Analyze current crypto market conditions and generate trading signals.

## Market Data

### Fear & Greed Index
{json.dumps(fng, indent=2)}

### Recent News Headlines
{json.dumps((news + rss)[:20], indent=2)}

### Freqtrade Bot Status (current open trades)
{json.dumps(ft_status[:5], indent=2)}

### Freqtrade Performance
{json.dumps(ft_perf[:10], indent=2)}

### Current Open Positions (skip these pairs)
{open_pairs}

### Sage Learning Insights
{json.dumps(sage_insights, indent=2)}

## Task
Generate trading signals for: {TRADING_PAIRS}
Skip pairs with open positions. Return JSON as specified in your system prompt."""

        result = await self.think_json(
            [{"role": "user", "content": prompt}]
        )

        regime = result.get("regime", "SIDEWAYS")
        await self.save_memory("current_regime", {"regime": regime, "updated": datetime.utcnow().isoformat()})

        signals = result.get("signals", [])
        await self.emit_status(f"Generated {len(signals)} signals (regime: {regime})")

        # Publish research update to dashboard
        await self.publish(AtlasMessage(
            source_agent=AgentID.ORACLE,
            message_type=MessageType.RESEARCH_UPDATE,
            payload={
                "regime": regime,
                "market_summary": result.get("market_summary", ""),
                "signal_count": len(signals),
                "fear_greed": fng,
            },
        ))

        # Process and persist each signal
        for sig in signals:
            if sig.get("confidence", 0) < 0.6:
                continue
            signal_id = await self._persist_signal(sig)
            await self.publish(AtlasMessage(
                source_agent=AgentID.ORACLE,
                message_type=MessageType.MARKET_SIGNAL,
                payload={**sig, "signal_id": signal_id},
                priority=4 if sig["confidence"] > 0.8 else 3,
            ))
            logger.info("[Oracle] Signal published: %s %s conf=%.2f",
                        sig["pair"], sig["direction"], sig["confidence"])

    async def _persist_signal(self, sig: dict) -> str:
        async with get_session() as sess:
            row = await sess.execute(text("""
                INSERT INTO signals (pair, direction, confidence, reasoning,
                                     entry_price, stop_loss, take_profit)
                VALUES (:pair, :dir, :conf, :reason, :entry, :sl, :tp)
                RETURNING id
            """), {
                "pair": sig["pair"],
                "dir": sig["direction"],
                "conf": sig.get("confidence"),
                "reason": sig.get("reasoning", ""),
                "entry": sig.get("entry_price"),
                "sl": sig.get("stop_loss"),
                "tp": sig.get("take_profit"),
            })
            signal_id = str(row.fetchone()[0])
            await sess.commit()
        return signal_id

    async def process_message(self, msg: AtlasMessage) -> None:
        if msg.message_type == MessageType.CHAT_MESSAGE and msg.target_agent == AgentID.ORACLE:
            await self._on_chat(msg)

    async def _on_chat(self, msg: AtlasMessage) -> None:
        ctx = await self.build_shared_context()
        response = await self.think(
            [{"role": "user", "content": msg.payload.get("content", "")}],
            system=PERSONALITY + f"\n\nCurrent market regime: {await self.load_memory('current_regime')}",
        )
        await self.publish(AtlasMessage(
            source_agent=AgentID.ORACLE,
            message_type=MessageType.CHAT_RESPONSE,
            payload={"content": response, "session_id": msg.payload.get("session_id")},
            correlation_id=msg.id,
        ))


async def main():
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    agent = OracleAgent(get_settings())
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
