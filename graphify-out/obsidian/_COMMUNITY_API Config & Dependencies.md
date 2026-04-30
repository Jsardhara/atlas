---
type: community
cohesion: 0.06
members: 49
---

# API Config & Dependencies

**Cohesion:** 0.06 - loosely connected
**Members:** 49 nodes

## Members
- [[API Lifespan (startupshutdown)]] - code - api/main.py
- [[API Settings (Pydantic BaseSettings)]] - code - api/config.py
- [[ATLAS FastAPI App Instance]] - code - api/main.py
- [[Agents Router (agents)]] - code - api/routers/agents.py
- [[ConnectionManager (WebSocket broadcast)]] - code - api/websocket/manager.py
- [[DB Table agents]] - code - api/routers/agents.py
- [[DB Table alerts]] - code - api/routers/system.py
- [[DB Table backtests]] - code - api/routers/strategies.py
- [[DB Table chat_messages]] - code - api/routers/agents.py
- [[DB Table portfolio_snapshots]] - code - agents/trader/kraken_executor.py
- [[DB Table signals]] - code - api/routers/signals.py
- [[DB Table strategies]] - code - api/routers/strategies.py
- [[DB Table trades]] - code - agents/trader/kraken_executor.py
- [[KrakenExecutor_1]] - code - agents/trader/kraken_executor.py
- [[KrakenExecutor.close_trade]] - code - agents/trader/kraken_executor.py
- [[KrakenExecutor.execute_trade]] - code - agents/trader/kraken_executor.py
- [[Next.js Config (ATLAS Dashboard)]] - code - dashboard/next.config.ts
- [[Paper Trading Gate (live_trading_enabled flag)]] - code - agents/trader/kraken_executor.py
- [[Portfolio Router (portfolio)]] - code - api/routers/portfolio.py
- [[Redis Stream atlasevents (message bus)]] - code - api/main.py
- [[SSE Streaming Pattern (Redis - HTTP clients)]] - code - api/routers/terminal.py
- [[Signals Router (signals)]] - code - api/routers/signals.py
- [[Stop-Loss  Take-Profit Monitoring Pattern]] - code - agents/trader/agent.py
- [[Strategies Router (strategies)]] - code - api/routers/strategies.py
- [[System Router (system)]] - code - api/routers/system.py
- [[Terminal Router (terminal)]] - code - api/routers/terminal.py
- [[Trader Agent Personality Prompt]] - code - agents/trader/agent.py
- [[TraderAgent_1]] - code - agents/trader/agent.py
- [[TraderAgent._execute_trade]] - code - agents/trader/agent.py
- [[TraderAgent._monitor_open_positions]] - code - agents/trader/agent.py
- [[TraderAgent._on_chat]] - code - agents/trader/agent.py
- [[TraderAgent._publish_close]] - code - agents/trader/agent.py
- [[TraderAgent.process_message]] - code - agents/trader/agent.py
- [[Trades Router (trades)]] - code - api/routers/trades.py
- [[WebSocket-Redis Bridge Pattern]] - code - api/websocket/router.py
- [[_send_command (pauseresume agent)]] - code - api/routers/agents.py
- [[chat_with_agent endpoint]] - code - api/routers/agents.py
- [[generate_strategy (triggers Architect)]] - code - api/routers/strategies.py
- [[get_db (async session context manager)]] - code - api/dependencies.py
- [[get_settings (lru_cache factory)]] - code - api/config.py
- [[health endpoint (Postgres + Redis + agents)]] - code - api/routers/system.py
- [[init_db (async engine setup)]] - code - api/dependencies.py
- [[manual_close_trade endpoint]] - code - api/routers/trades.py
- [[override_signal (manual approvereject)]] - code - api/routers/signals.py
- [[paper_readiness endpoint]] - code - api/routers/system.py
- [[send_message (Master Control Terminal)]] - code - api/routers/terminal.py
- [[stream_chat SSE endpoint]] - code - api/routers/agents.py
- [[terminal_feed (SSE all agent events)]] - code - api/routers/terminal.py
- [[websocket_endpoint (ws)]] - code - api/websocket/router.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/API_Config_&_Dependencies
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Trade Execution Engine]]

## Top bridge nodes
- [[DB Table trades]] - degree 6, connects to 1 community
- [[TraderAgent._execute_trade]] - degree 4, connects to 1 community
- [[DB Table portfolio_snapshots]] - degree 2, connects to 1 community