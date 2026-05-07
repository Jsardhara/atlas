---
type: community
cohesion: 0.11
members: 33
---

# Dashboard UI Layer

**Cohesion:** 0.11 - loosely connected
**Members:** 33 nodes

## Members
- [[@agent Routing Syntax]] - code - dashboard/src/components/terminal/MasterTerminal.tsx
- [[API Client Library]] - code - dashboard/src/lib/api.ts
- [[API URL Config (NEXT_PUBLIC_API_URL)]] - code - dashboard/src/lib/api.ts
- [[Agent Detail Page]] - code - dashboard/src/app/agents/[id]/page.tsx
- [[Agent Type]] - code - dashboard/src/lib/api.ts
- [[AgentCard Component]] - code - dashboard/src/components/agents/AgentCard.tsx
- [[AgentChat Component]] - code - dashboard/src/components/agents/AgentChat.tsx
- [[AgentDetail Type]] - code - dashboard/src/lib/api.ts
- [[Agents Page]] - code - dashboard/src/app/agents/page.tsx
- [[Alert Type]] - code - dashboard/src/lib/api.ts
- [[AlertBanner Component]] - code - dashboard/src/components/shared/AlertBanner.tsx
- [[Atlas Zustand Store]] - code - dashboard/src/store/index.ts
- [[Live Event Feed (recentEvents ring buffer)]] - code - dashboard/src/store/index.ts
- [[MasterTerminal Component]] - code - dashboard/src/components/terminal/MasterTerminal.tsx
- [[Overview Page]] - code - dashboard/src/app/page.tsx
- [[PaperReadiness Type]] - code - dashboard/src/lib/api.ts
- [[Portfolio Page]] - code - dashboard/src/app/portfolio/page.tsx
- [[Portfolio Type]] - code - dashboard/src/lib/api.ts
- [[PortfolioSnapshot Type]] - code - dashboard/src/lib/api.ts
- [[Root Layout]] - code - dashboard/src/app/layout.tsx
- [[Sidebar Component]] - code - dashboard/src/components/shared/Sidebar.tsx
- [[Strategies Page]] - code - dashboard/src/app/strategies/page.tsx
- [[Strategy Type]] - code - dashboard/src/lib/api.ts
- [[StrategyDetail Type]] - code - dashboard/src/lib/api.ts
- [[Terminal Page]] - code - dashboard/src/app/terminal/page.tsx
- [[Trade Type]] - code - dashboard/src/lib/api.ts
- [[TradeStats Type]] - code - dashboard/src/lib/api.ts
- [[Trades Page]] - code - dashboard/src/app/trades/page.tsx
- [[WSMessage Type]] - code - dashboard/src/hooks/useWebSocket.ts
- [[WSProvider Component]] - code - dashboard/src/components/shared/WSProvider.tsx
- [[WebSocket Auto-Reconnect (3s backoff)]] - code - dashboard/src/hooks/useWebSocket.ts
- [[WebSocket URL Config (NEXT_PUBLIC_WS_URL)]] - code - dashboard/src/hooks/useWebSocket.ts
- [[useWebSocket Hook]] - code - dashboard/src/hooks/useWebSocket.ts

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Dashboard_UI_Layer
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Live Trading Gate]]

## Top bridge nodes
- [[Overview Page]] - degree 6, connects to 1 community
- [[@agent Routing Syntax]] - degree 2, connects to 1 community