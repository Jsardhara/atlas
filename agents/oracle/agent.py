"""Oracle — Research and signal generation agent."""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import text

from shared.base_agent import BaseAgent
from shared.config import get_settings
from shared.db import get_session
from shared.protocols import AgentID, AtlasMessage, MessageType

from .data_sources.freqtrade import FreqtradeClient
from .data_sources.kraken_market import discover_universe
from .data_sources.news import fetch_cryptopanic, fetch_fear_and_greed, fetch_rss_headlines
from .screener import DEFAULT_TOP_N, screen_universe

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

SCAN_INTERVAL = 900  # 15 minutes
SCREENER_TOP_N = DEFAULT_TOP_N


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

        # Stage 1 — universe + cheap screener (no LLM)
        await self.emit_status("Discovering Kraken USD universe")
        universe = await discover_universe()
        candidates = await screen_universe(universe, top_n=SCREENER_TOP_N)
        candidate_pairs = [c.pair for c in candidates] or [info.wsname for info in universe[:4]]
        shortable_set = sorted({info.wsname for info in universe if info.shortable})
        logger.info(
            "[Oracle] Screener selected %d/%d pairs (shortable=%d)",
            len(candidates), len(universe), len(shortable_set),
        )

        # Stage 2 — external context + LLM analyzes screener candidates
        await self.emit_status("Fetching market data")
        news, rss, fng, ft_status, ft_perf, ctx = await asyncio.gather(
            fetch_cryptopanic(self.settings.cryptopanic_api_key, candidate_pairs),
            fetch_rss_headlines(),
            fetch_fear_and_greed(),
            self.freqtrade.get_status(),
            self.freqtrade.get_performance(),
            self.build_shared_context(),
        )

        await self.emit_status("Analyzing market conditions")

        sage_insights = ctx.get("sage_insights", {})
        open_pairs = [p["pair"] for p in ctx.get("open_positions", [])]

        screener_lines = [
            f"- {c.pair} score={c.score:+.2f} dir={c.suggested_direction} "
            f"shortable={c.shortable} {c.snapshot.get('indicators', '')}"
            for c in candidates
        ]

        prompt = f"""Analyze current crypto market conditions and generate trading signals.

### Screener Top Candidates (Stage 1, pre-LLM)
{chr(10).join(screener_lines) if screener_lines else "(no screener output — fallback to candidate_pairs)"}

### Shortable Pairs (margin-eligible on Kraken)
{shortable_set}


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
Generate trading signals for the screener candidates above (top {SCREENER_TOP_N}).
Skip pairs with open positions. If a candidate's suggested direction is SHORT but
its pair is NOT in the Shortable set, downgrade to NEUTRAL.
Return JSON as specified in your system prompt."""

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
