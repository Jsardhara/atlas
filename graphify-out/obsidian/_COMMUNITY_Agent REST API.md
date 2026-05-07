---
type: community
cohesion: 0.05
members: 43
---

# Agent REST API

**Cohesion:** 0.05 - loosely connected
**Members:** 43 nodes

## Members
- [[Agent control, status, and individual chat routes.]] - rationale - C:\Users\jyot2\atlas\api\routers\agents.py
- [[FastAPI dependency injection helpers.]] - rationale - C:\Users\jyot2\atlas\api\dependencies.py
- [[SSE stream of chat responses for a session.]] - rationale - C:\Users\jyot2\atlas\api\routers\agents.py
- [[Signal Trader agent to close this position immediately.]] - rationale - C:\Users\jyot2\atlas\api\routers\trades.py
- [[Tell Architect to generate a new strategy.]] - rationale - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[Trade management routes.]] - rationale - C:\Users\jyot2\atlas\api\routers\trades.py
- [[User manually approve or reject a pending signal.]] - rationale - C:\Users\jyot2\atlas\api\routers\signals.py
- [[_send_command()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[activate_strategy()]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[active_signals()]] - code - C:\Users\jyot2\atlas\api\routers\signals.py
- [[agents.py]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[archive_strategy()]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[chat_with_agent()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[current_portfolio()]] - code - C:\Users\jyot2\atlas\api\routers\portfolio.py
- [[dependencies.py]] - code - C:\Users\jyot2\atlas\api\dependencies.py
- [[generate_strategy()]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[get_agent()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[get_alerts()]] - code - C:\Users\jyot2\atlas\api\routers\system.py
- [[get_db()]] - code - C:\Users\jyot2\atlas\api\dependencies.py
- [[get_memory()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[get_open_trades()]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[get_strategy()]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[get_trade()]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[health()]] - code - C:\Users\jyot2\atlas\api\routers\system.py
- [[init_db()_1]] - code - C:\Users\jyot2\atlas\api\dependencies.py
- [[list_agents()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[list_signals()]] - code - C:\Users\jyot2\atlas\api\routers\signals.py
- [[list_strategies()]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[list_trades()]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[manual_close_trade()]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[override_signal()]] - code - C:\Users\jyot2\atlas\api\routers\signals.py
- [[paper_readiness()]] - code - C:\Users\jyot2\atlas\api\routers\system.py
- [[pause_agent()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[portfolio.py]] - code - C:\Users\jyot2\atlas\api\routers\portfolio.py
- [[portfolio_history()]] - code - C:\Users\jyot2\atlas\api\routers\portfolio.py
- [[resume_agent()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[signals.py]] - code - C:\Users\jyot2\atlas\api\routers\signals.py
- [[strategies.py]] - code - C:\Users\jyot2\atlas\api\routers\strategies.py
- [[stream_chat()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[system.py]] - code - C:\Users\jyot2\atlas\api\routers\system.py
- [[trade_stats()]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[trades.py]] - code - C:\Users\jyot2\atlas\api\routers\trades.py
- [[update_config()]] - code - C:\Users\jyot2\atlas\api\routers\agents.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Agent_REST_API
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Agent Protocol Layer]]
- 1 edge to [[_COMMUNITY_WebSocket & API Core]]

## Top bridge nodes
- [[agents.py]] - degree 13, connects to 1 community
- [[dependencies.py]] - degree 10, connects to 1 community