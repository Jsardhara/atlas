---
type: community
cohesion: 0.08
members: 43
---

# Strategy & Alert System

**Cohesion:** 0.08 - loosely connected
**Members:** 43 nodes

## Members
- [[Agent Memory (agent_memory table)]] - document - agents/shared/base_agent.py
- [[AgentID Enum]] - code - agents/shared/protocols.py
- [[AlertManager_1]] - code - agents/commander/alert_manager.py
- [[ArchitectAgent_1]] - code - agents/architect/agent.py
- [[Async SQLAlchemy engine and session factory.]] - rationale - C:\Users\jyot2\atlas\agents\shared\db.py
- [[AtlasMessage_1]] - code - agents/shared/protocols.py
- [[Base]] - code - C:\Users\jyot2\atlas\agents\shared\db.py
- [[BaseAgent_2]] - code - agents/shared/base_agent.py
- [[CommanderAgent_1]] - code - agents/commander/agent.py
- [[CryptoPanic + RSS news fetcher.]] - rationale - C:\Users\jyot2\atlas\agents\oracle\data_sources\news.py
- [[Daily Loss Circuit Breaker]] - document - agents/guardian/validators/hard_rules.py
- [[DeclarativeBase]] - code
- [[Freqtrade Strategy (generated artifact)]] - document - agents/architect/agent.py
- [[FreqtradeClient_1]] - code - agents/oracle/data_sources/freqtrade.py
- [[GuardianAgent_1]] - code - agents/guardian/agent.py
- [[Hard rule validators — no LLM, pure logic.]] - rationale - C:\Users\jyot2\atlas\agents\guardian\validators\hard_rules.py
- [[KrakenClient_1]] - code - agents/shared/kraken_client.py
- [[MessageBus_1]] - code - agents/shared/message_bus.py
- [[OpenRouterClient_1]] - code - agents/shared/openrouter_client.py
- [[OracleAgent_1]] - code - agents/oracle/agent.py
- [[Sage Insights (shared learning context)]] - document - agents/sage/agent.py
- [[SageAgent_1]] - code - agents/sage/agent.py
- [[Settings_1]] - code - agents/shared/config.py
- [[Trading Signal Pipeline]] - document - agents/shared/protocols.py
- [[ValidationResult_1]] - code - agents/guardian/validators/hard_rules.py
- [[ValidationResult]] - code - C:\Users\jyot2\atlas\agents\guardian\validators\hard_rules.py
- [[agent.py_2]] - code - C:\Users\jyot2\atlas\agents\guardian\agent.py
- [[build_shared_context]] - code - agents/shared/base_agent.py
- [[close_db()]] - code - C:\Users\jyot2\atlas\agents\shared\db.py
- [[db.py]] - code - C:\Users\jyot2\atlas\agents\shared\db.py
- [[fetch_cryptopanic()]] - code - C:\Users\jyot2\atlas\agents\oracle\data_sources\news.py
- [[fetch_fear_and_greed()]] - code - C:\Users\jyot2\atlas\agents\oracle\data_sources\news.py
- [[fetch_rss_headlines()]] - code - C:\Users\jyot2\atlas\agents\oracle\data_sources\news.py
- [[get_session()]] - code - C:\Users\jyot2\atlas\agents\shared\db.py
- [[hard_rules.py]] - code - C:\Users\jyot2\atlas\agents\guardian\validators\hard_rules.py
- [[init_db()]] - code - C:\Users\jyot2\atlas\agents\shared\db.py
- [[load_memory]] - code - agents/shared/base_agent.py
- [[news.py]] - code - C:\Users\jyot2\atlas\agents\oracle\data_sources\news.py
- [[run_backtest()]] - code - C:\Users\jyot2\atlas\agents\architect\backtest_runner.py
- [[save_memory]] - code - agents/shared/base_agent.py
- [[think]] - code - agents/shared/base_agent.py
- [[think_json]] - code - agents/shared/base_agent.py
- [[validate_hard_rules()]] - code - C:\Users\jyot2\atlas\agents\guardian\validators\hard_rules.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Strategy_&_Alert_System
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Guardian Risk Layer]]
- 2 edges to [[_COMMUNITY_Strategy Architect]]
- 1 edge to [[_COMMUNITY_Agent Protocol Layer]]
- 1 edge to [[_COMMUNITY_Agent Base Infrastructure]]

## Top bridge nodes
- [[agent.py_2]] - degree 4, connects to 2 communities
- [[ArchitectAgent_1]] - degree 8, connects to 1 community
- [[db.py]] - degree 6, connects to 1 community
- [[news.py]] - degree 5, connects to 1 community
- [[run_backtest()]] - degree 4, connects to 1 community