---
type: community
cohesion: 0.29
members: 7
---

# Terminal Interface

**Cohesion:** 0.29 - loosely connected
**Members:** 7 nodes

## Members
- [[Master Control Terminal routes.]] - rationale - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[Route a message to a specific agent using @name prefix, or Commander by default.]] - rationale - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[SSE stream of all agent decisions and status updates.]] - rationale - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[TerminalMessage]] - code - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[send_message()]] - code - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[terminal.py]] - code - C:\Users\jyot2\atlas\api\routers\terminal.py
- [[terminal_feed()]] - code - C:\Users\jyot2\atlas\api\routers\terminal.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Terminal_Interface
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Agent Protocol Layer]]

## Top bridge nodes
- [[TerminalMessage]] - degree 2, connects to 1 community