---
type: community
cohesion: 0.08
members: 38
---

# Trade Execution Engine

**Cohesion:** 0.08 - loosely connected
**Members:** 38 nodes

## Members
- [[.__init__()_9]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[.__init__()_6]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.__init__()_10]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[._execute_trade()]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[._init_client()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[._monitor_open_positions()]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[._on_chat()_5]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[._publish_close()]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[._run_loop()_5]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[.cancel_order()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.close_trade()]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[.execute_trade()]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[.get_balance()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.get_open_orders()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.get_ticker()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.get_trade_history()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.place_order()]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[.process_message()_5]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[.size_position()]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[BaseSettings]] - code
- [[Calculate position size using Kelly criterion + risk limits.]] - rationale - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[Kelly Criterion Position Sizing]] - code - agents/trader/kraken_executor.py
- [[Kraken REST API wrapper using python-kraken-sdk.]] - rationale - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[KrakenClient]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[KrakenExecutor]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[KrakenExecutor.size_position]] - code - agents/trader/kraken_executor.py
- [[Place an order. validate=True for paper trading (no real execution).]] - rationale - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[Settings]] - code - C:\Users\jyot2\atlas\api\config.py
- [[Thin wrapper around python-kraken-sdk for spotmargin trading.]] - rationale - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[Trader Kraken execution layer — places and monitors orders.]] - rationale - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[TraderAgent]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[agent.py_5]] - code - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[config.py]] - code - C:\Users\jyot2\atlas\agents\shared\config.py
- [[config.py_1]] - code - C:\Users\jyot2\atlas\api\config.py
- [[get_settings()]] - code - C:\Users\jyot2\atlas\api\config.py
- [[kelly_fraction()]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py
- [[kraken_client.py]] - code - C:\Users\jyot2\atlas\agents\shared\kraken_client.py
- [[kraken_executor.py]] - code - C:\Users\jyot2\atlas\agents\trader\kraken_executor.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Trade_Execution_Engine
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Agent Protocol Layer]]
- 3 edges to [[_COMMUNITY_Guardian Risk Layer]]
- 3 edges to [[_COMMUNITY_Agent Base Infrastructure]]
- 3 edges to [[_COMMUNITY_API Config & Dependencies]]
- 1 edge to [[_COMMUNITY_WebSocket & API Core]]

## Top bridge nodes
- [[TraderAgent]] - degree 16, connects to 3 communities
- [[Settings]] - degree 16, connects to 2 communities
- [[agent.py_5]] - degree 4, connects to 2 communities
- [[KrakenClient]] - degree 16, connects to 1 community
- [[KrakenExecutor]] - degree 9, connects to 1 community