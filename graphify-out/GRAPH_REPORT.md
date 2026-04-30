# Graph Report - C:/Users/jyot2/atlas  (2026-04-12)

## Corpus Check
- Corpus is ~16,685 words - fits in a single context window. You may not need a graph.

## Summary
- 408 nodes · 633 edges · 47 communities detected
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 140 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_API Config & Dependencies|API Config & Dependencies]]
- [[_COMMUNITY_Strategy & Alert System|Strategy & Alert System]]
- [[_COMMUNITY_Agent REST API|Agent REST API]]
- [[_COMMUNITY_Trade Execution Engine|Trade Execution Engine]]
- [[_COMMUNITY_Agent Protocol Layer|Agent Protocol Layer]]
- [[_COMMUNITY_Dashboard UI Layer|Dashboard UI Layer]]
- [[_COMMUNITY_Guardian Risk Layer|Guardian Risk Layer]]
- [[_COMMUNITY_Agent Base Infrastructure|Agent Base Infrastructure]]
- [[_COMMUNITY_WebSocket & API Core|WebSocket & API Core]]
- [[_COMMUNITY_Commander Orchestration|Commander Orchestration]]
- [[_COMMUNITY_Dashboard Pages|Dashboard Pages]]
- [[_COMMUNITY_Live Trading Gate|Live Trading Gate]]
- [[_COMMUNITY_Strategy Architect|Strategy Architect]]
- [[_COMMUNITY_Terminal Interface|Terminal Interface]]
- [[_COMMUNITY_Trading Protocols|Trading Protocols]]
- [[_COMMUNITY_App Layout|App Layout]]
- [[_COMMUNITY_Terminal Page|Terminal Page]]
- [[_COMMUNITY_Agent Card UI|Agent Card UI]]
- [[_COMMUNITY_Agent Chat UI|Agent Chat UI]]
- [[_COMMUNITY_WebSocket Provider|WebSocket Provider]]
- [[_COMMUNITY_Master Terminal|Master Terminal]]
- [[_COMMUNITY_WebSocket Hook|WebSocket Hook]]
- [[_COMMUNITY_API Client|API Client]]
- [[_COMMUNITY_Dashboard Config|Dashboard Config]]
- [[_COMMUNITY_Requirements|Requirements]]
- [[_COMMUNITY_Architect Module|Architect Module]]
- [[_COMMUNITY_Commander Module|Commander Module]]
- [[_COMMUNITY_Guardian Module|Guardian Module]]
- [[_COMMUNITY_Oracle Module|Oracle Module]]
- [[_COMMUNITY_Sage Module|Sage Module]]
- [[_COMMUNITY_Shared Module|Shared Module]]
- [[_COMMUNITY_Trader Module|Trader Module]]
- [[_COMMUNITY_API Module|API Module]]
- [[_COMMUNITY_Routers Module|Routers Module]]
- [[_COMMUNITY_WebSocket Module|WebSocket Module]]
- [[_COMMUNITY_Next.js Config|Next.js Config]]
- [[_COMMUNITY_PostCSS Config|PostCSS Config]]
- [[_COMMUNITY_Tailwind Config|Tailwind Config]]
- [[_COMMUNITY_Alert Banner|Alert Banner]]
- [[_COMMUNITY_Sidebar Nav|Sidebar Nav]]
- [[_COMMUNITY_Global Store|Global Store]]
- [[_COMMUNITY_Message Types|Message Types]]
- [[_COMMUNITY_Agent State|Agent State]]
- [[_COMMUNITY_Agent Commands|Agent Commands]]
- [[_COMMUNITY_Shared Init|Shared Init]]
- [[_COMMUNITY_Trader Entry|Trader Entry]]
- [[_COMMUNITY_Chat Request|Chat Request]]

## God Nodes (most connected - your core abstractions)
1. `BaseAgent` - 31 edges
2. `CommanderAgent` - 20 edges
3. `AgentID` - 20 edges
4. `AtlasMessage` - 19 edges
5. `MessageType` - 18 edges
6. `Trader — Order execution agent.` - 17 edges
7. `Settings` - 16 edges
8. `KrakenClient` - 16 edges
9. `MessageBus` - 16 edges
10. `TraderAgent` - 16 edges

## Surprising Connections (you probably didn't know these)
- `@agent Routing Syntax` --conceptually_related_to--> `Commander Supervisor Prompt`  [INFERRED]
  dashboard/src/components/terminal/MasterTerminal.tsx → agents/commander/prompts/supervisor.md
- `FreqtradeClient` --semantically_similar_to--> `run_backtest()`  [INFERRED] [semantically similar]
  agents/oracle/data_sources/freqtrade.py → C:\Users\jyot2\atlas\agents\architect\backtest_runner.py
- `Paper Trading Mode (Safety Concept)` --conceptually_related_to--> `Paper-to-Live Readiness Thresholds`  [INFERRED]
  README.md → dashboard/src/app/page.tsx
- `Paper-to-Live Readiness Thresholds` --implements--> `Live Trading Readiness Gate`  [INFERRED]
  dashboard/src/app/page.tsx → README.md
- `ArchitectAgent` --uses--> `BaseAgent`  [INFERRED]
  C:\Users\jyot2\atlas\agents\architect\agent.py → C:\Users\jyot2\atlas\agents\shared\base_agent.py

## Hyperedges (group relationships)
- **Oracle → Commander → Guardian Signal Pipeline** — oracle_agent_OracleAgent, commander_agent_CommanderAgent, guardian_agent_GuardianAgent [EXTRACTED 0.97]
- **Sage Insight Consumer Triad (Oracle, Guardian, Architect)** — oracle_agent_OracleAgent, guardian_agent_GuardianAgent, architect_agent_ArchitectAgent [EXTRACTED 0.95]
- **Risk Enforcement Layer (hard_rules + Commander circuit breaker + Settings limits)** — hard_rules_validate_hard_rules, commander_agent_CommanderAgent, config_Settings [INFERRED 0.82]
- **Trade Execution Pipeline: signal approval -> TraderAgent -> KrakenExecutor -> DB + bus** — trader_agent_execute_trade, kraken_executor_size_position, kraken_executor_execute_trade, shared_db_trades_table, shared_redis_stream_atlas_events [EXTRACTED 0.97]
- **Redis atlas:events Fan-Out: all API routers and WS endpoint share one stream key** — shared_redis_stream_atlas_events, api_routers_agents_chat_with_agent, api_routers_signals_override_signal, api_routers_trades_manual_close, api_routers_terminal_send_message, api_routers_terminal_feed, api_websocket_router_websocket_endpoint [EXTRACTED 1.00]
- **Position Risk Management: Kelly sizing + stop-loss/take-profit monitoring + paper gate** — concept_kelly_criterion, concept_stop_loss_monitoring, concept_paper_trading_gate, kraken_executor_size_position, trader_agent_monitor_open_positions [INFERRED 0.88]
- **WebSocket Real-Time Event Pipeline (useWebSocket → useAtlasStore → UI components)** — useWebSocket, WSProvider, useAtlasStore, AlertBanner, AgentCard, MasterTerminal [EXTRACTED 0.95]
- **Agent Chat Pattern (AgentChat + MasterTerminal share session-ID chat over WS + REST)** — AgentChat, MasterTerminal, useWebSocket, api_lib [EXTRACTED 0.92]
- **Paper-to-Live Trading Gate (PaperReadiness thresholds gate live trading enablement)** — paper_readiness_check, readme_LiveTradingReadiness, readme_PaperTradingMode, readme_SafetyLimits [INFERRED 0.85]

## Communities

### Community 0 - "API Config & Dependencies"
Cohesion: 0.06
Nodes (49): API Settings (Pydantic BaseSettings), get_settings (lru_cache factory), get_db (async session context manager), init_db (async engine setup), ATLAS FastAPI App Instance, API Lifespan (startup/shutdown), chat_with_agent endpoint, Agents Router (/agents) (+41 more)

### Community 1 - "Strategy & Alert System"
Cohesion: 0.08
Nodes (38): AlertManager, ArchitectAgent, run_backtest(), BaseAgent, build_shared_context, load_memory, save_memory, think (+30 more)

### Community 2 - "Agent REST API"
Cohesion: 0.05
Nodes (14): pause_agent(), Agent control, status, and individual chat routes., SSE stream of chat responses for a session., resume_agent(), _send_command(), stream_chat(), FastAPI dependency injection helpers., override_signal() (+6 more)

### Community 3 - "Trade Execution Engine"
Cohesion: 0.08
Nodes (14): TraderAgent, BaseSettings, Kelly Criterion Position Sizing, get_settings(), Settings, KrakenClient, Kraken REST API wrapper using python-kraken-sdk., Thin wrapper around python-kraken-sdk for spot/margin trading. (+6 more)

### Community 4 - "Agent Protocol Layer"
Cohesion: 0.13
Nodes (23): Trader — Order execution agent., Evaluate whether to advance the signal through the pipeline., ChatRequest, ConfigPatch, AlertManager, Commander alert manager — creates DB alerts and publishes to the dashboard., Abstract BaseAgent — all 6 agents extend this., Load common context injected into every agent's prompts. (+15 more)

### Community 5 - "Dashboard UI Layer"
Cohesion: 0.11
Nodes (33): API URL Config (NEXT_PUBLIC_API_URL), @agent Routing Syntax, AgentCard Component, AgentChat Component, AgentDetail Type, Agent Type, AlertBanner Component, Alert Type (+25 more)

### Community 6 - "Guardian Risk Layer"
Cohesion: 0.1
Nodes (7): GuardianAgent, main(), OracleAgent, SageAgent, BaseAgent, FreqtradeClient, Fetch FreqAI predictions from the running Freqtrade instance.

### Community 7 - "Agent Base Infrastructure"
Cohesion: 0.11
Nodes (6): ABC, BaseAgent, process_message(), _run_loop(), OpenRouterClient, OpenRouter client — OpenAI-compatible API with retry and cost tracking.

### Community 8 - "WebSocket & API Core"
Cohesion: 0.15
Nodes (4): ATLAS FastAPI application., ConnectionManager, WebSocket connection manager — broadcasts all Atlas events to dashboard clients., WebSocket endpoint — streams all Atlas bus events to authenticated clients.

### Community 9 - "Commander Orchestration"
Cohesion: 0.31
Nodes (1): CommanderAgent

### Community 10 - "Dashboard Pages"
Cohesion: 0.24
Nodes (4): handleActivate(), load(), openStrategy(), toggle()

### Community 11 - "Live Trading Gate"
Cohesion: 0.24
Nodes (11): Paper-to-Live Readiness Thresholds, ATLAS System README, Six Agent Roles, Live Trading Readiness Gate, Paper Trading Mode (Safety Concept), Safety Limits (Risk Controls), Oracle-Guardian-Trader Signal Pipeline, Circuit Breaker / Agent Pause Logic (+3 more)

### Community 12 - "Strategy Architect"
Cohesion: 0.27
Nodes (4): ArchitectAgent, Run Freqtrade backtests via Docker SDK., Extract key metrics from Freqtrade backtest JSON., score_backtest()

### Community 13 - "Terminal Interface"
Cohesion: 0.29
Nodes (6): Master Control Terminal routes., Route a message to a specific agent using @name prefix, or Commander by default., SSE stream of all agent decisions and status updates., send_message(), terminal_feed(), TerminalMessage

### Community 14 - "Trading Protocols"
Cohesion: 0.67
Nodes (3): MarketSignal, OrderParams, TradeDecision

### Community 15 - "App Layout"
Cohesion: 1.0
Nodes (0): 

### Community 16 - "Terminal Page"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Agent Card UI"
Cohesion: 1.0
Nodes (0): 

### Community 18 - "Agent Chat UI"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "WebSocket Provider"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Master Terminal"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "WebSocket Hook"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "API Client"
Cohesion: 1.0
Nodes (0): 

### Community 23 - "Dashboard Config"
Cohesion: 1.0
Nodes (2): PostCSS Config (Dashboard), Tailwind CSS Config (Dashboard)

### Community 24 - "Requirements"
Cohesion: 1.0
Nodes (2): Agents Python Requirements, API Python Requirements

### Community 25 - "Architect Module"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Commander Module"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Guardian Module"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Oracle Module"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Sage Module"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Shared Module"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Trader Module"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "API Module"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Routers Module"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "WebSocket Module"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Next.js Config"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "PostCSS Config"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Tailwind Config"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Alert Banner"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Sidebar Nav"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Global Store"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Message Types"
Cohesion: 1.0
Nodes (1): MessageType Enum

### Community 42 - "Agent State"
Cohesion: 1.0
Nodes (1): AgentState Enum

### Community 43 - "Agent Commands"
Cohesion: 1.0
Nodes (1): AgentCommand Enum

### Community 44 - "Shared Init"
Cohesion: 1.0
Nodes (1): agents/shared __init__

### Community 45 - "Trader Entry"
Cohesion: 1.0
Nodes (1): Trader Agent Entry Point (main)

### Community 46 - "Chat Request"
Cohesion: 1.0
Nodes (1): ChatRequest (Pydantic model)

## Knowledge Gaps
- **64 isolated node(s):** `Run Freqtrade backtests via Docker SDK.`, `Extract key metrics from Freqtrade backtest JSON.`, `Hard rule validators — no LLM, pure logic.`, `Fetch FreqAI predictions from the running Freqtrade instance.`, `CryptoPanic + RSS news fetcher.` (+59 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `App Layout`** (2 nodes): `layout.tsx`, `RootLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Terminal Page`** (2 nodes): `page.tsx`, `TerminalPage()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Card UI`** (2 nodes): `handleToggle()`, `AgentCard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Chat UI`** (2 nodes): `send()`, `AgentChat.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WebSocket Provider`** (2 nodes): `WSProvider.tsx`, `WSProvider()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Master Terminal`** (2 nodes): `MasterTerminal.tsx`, `send()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WebSocket Hook`** (2 nodes): `useWebSocket.ts`, `useWebSocket()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Client`** (2 nodes): `request()`, `api.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Dashboard Config`** (2 nodes): `PostCSS Config (Dashboard)`, `Tailwind CSS Config (Dashboard)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Requirements`** (2 nodes): `Agents Python Requirements`, `API Python Requirements`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Architect Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Commander Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Guardian Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Oracle Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sage Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Shared Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Trader Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Routers Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WebSocket Module`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Next.js Config`** (1 nodes): `next.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PostCSS Config`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tailwind Config`** (1 nodes): `tailwind.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Alert Banner`** (1 nodes): `AlertBanner.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sidebar Nav`** (1 nodes): `Sidebar.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Global Store`** (1 nodes): `index.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Message Types`** (1 nodes): `MessageType Enum`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent State`** (1 nodes): `AgentState Enum`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Agent Commands`** (1 nodes): `AgentCommand Enum`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Shared Init`** (1 nodes): `agents/shared __init__`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Trader Entry`** (1 nodes): `Trader Agent Entry Point (main)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chat Request`** (1 nodes): `ChatRequest (Pydantic model)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `KrakenExecutor.size_position` connect `Trade Execution Engine` to `API Config & Dependencies`?**
  _High betweenness centrality (0.153) - this node is a cross-community bridge._
- **Why does `Settings` connect `Trade Execution Engine` to `Agent Protocol Layer`, `Agent Base Infrastructure`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `BaseAgent` (e.g. with `ArchitectAgent` and `Trader — Order execution agent.`) actually correct?**
  _`BaseAgent` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `CommanderAgent` (e.g. with `BaseAgent` and `AgentCommand`) actually correct?**
  _`CommanderAgent` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `AgentID` (e.g. with `ArchitectAgent` and `Trader — Order execution agent.`) actually correct?**
  _`AgentID` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `AtlasMessage` (e.g. with `ArchitectAgent` and `Trader — Order execution agent.`) actually correct?**
  _`AtlasMessage` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `MessageType` (e.g. with `ArchitectAgent` and `Trader — Order execution agent.`) actually correct?**
  _`MessageType` has 15 INFERRED edges - model-reasoned connections that need verification._