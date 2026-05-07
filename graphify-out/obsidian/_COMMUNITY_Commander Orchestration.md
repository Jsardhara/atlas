---
type: community
cohesion: 0.31
members: 11
---

# Commander Orchestration

**Cohesion:** 0.31 - loosely connected
**Members:** 11 nodes

## Members
- [[.__init__()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._check_pipeline_health()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_agent_status()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_chat()_1]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_market_signal()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_position_closed()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_trade_rejected()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._on_user_command()]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[._run_loop()_1]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[.process_message()_1]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[CommanderAgent]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Commander_Orchestration
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Agent Protocol Layer]]
- 2 edges to [[_COMMUNITY_Guardian Risk Layer]]
- 1 edge to [[_COMMUNITY_Agent Base Infrastructure]]

## Top bridge nodes
- [[CommanderAgent]] - degree 20, connects to 3 communities
- [[._on_market_signal()]] - degree 3, connects to 1 community