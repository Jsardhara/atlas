---
type: community
cohesion: 0.24
members: 11
---

# Live Trading Gate

**Cohesion:** 0.24 - loosely connected
**Members:** 11 nodes

## Members
- [[ATLAS System README]] - document - README.md
- [[Circuit Breaker  Agent Pause Logic]] - document - agents/commander/prompts/supervisor.md
- [[Commander Escalation Triggers]] - document - agents/commander/prompts/supervisor.md
- [[Commander JSON Decision Format]] - document - agents/commander/prompts/supervisor.md
- [[Commander Supervisor Prompt]] - document - agents/commander/prompts/supervisor.md
- [[Live Trading Readiness Gate]] - document - README.md
- [[Oracle-Guardian-Trader Signal Pipeline]] - document - README.md
- [[Paper Trading Mode (Safety Concept)]] - document - README.md
- [[Paper-to-Live Readiness Thresholds]] - code - dashboard/src/app/page.tsx
- [[Safety Limits (Risk Controls)]] - document - README.md
- [[Six Agent Roles]] - document - README.md

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Live_Trading_Gate
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Dashboard UI Layer]]

## Top bridge nodes
- [[Commander Supervisor Prompt]] - degree 5, connects to 1 community
- [[Paper-to-Live Readiness Thresholds]] - degree 3, connects to 1 community