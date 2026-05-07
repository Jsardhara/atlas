---
type: community
cohesion: 0.13
members: 36
---

# Agent Protocol Layer

**Cohesion:** 0.13 - loosely connected
**Members:** 36 nodes

## Members
- [[.__init__()_1]] - code - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[.__init__()_7]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[._ensure_groups()]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[.close()]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[.connect()]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[.consume()]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[.create_alert()]] - code - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[.publish()_1]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[.resolve_alert()]] - code - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[Abstract BaseAgent — all 6 agents extend this.]] - rationale - C:\Users\jyot2\atlas\agents\shared\base_agent.py
- [[AgentCommand]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[AgentID]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[AgentState]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[AlertManager]] - code - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[AtlasMessage]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[BaseModel]] - code
- [[ChatRequest]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[Commander alert manager — creates DB alerts and publishes to the dashboard.]] - rationale - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[ConfigPatch]] - code - C:\Users\jyot2\atlas\api\routers\agents.py
- [[Enum]] - code
- [[Evaluate whether to advance the signal through the pipeline.]] - rationale - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[Handle an incoming bus message.]] - rationale - C:\Users\jyot2\atlas\agents\shared\base_agent.py
- [[Load common context injected into every agent's prompts.]] - rationale - C:\Users\jyot2\atlas\agents\shared\base_agent.py
- [[Main agent work loop — scheduled tasks, polling, etc.]] - rationale - C:\Users\jyot2\atlas\agents\shared\base_agent.py
- [[MarketSignal]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[MessageBus]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[MessageType]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[OrderParams]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[Redis Streams message bus — fan-out to all agent consumer groups.]] - rationale - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[TradeDecision]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[Trader — Order execution agent.]] - rationale - C:\Users\jyot2\atlas\agents\trader\agent.py
- [[agent.py_1]] - code - C:\Users\jyot2\atlas\agents\commander\agent.py
- [[alert_manager.py]] - code - C:\Users\jyot2\atlas\agents\commander\alert_manager.py
- [[message_bus.py]] - code - C:\Users\jyot2\atlas\agents\shared\message_bus.py
- [[protocols.py]] - code - C:\Users\jyot2\atlas\agents\shared\protocols.py
- [[str]] - code

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Agent_Protocol_Layer
SORT file.name ASC
```

## Connections to other communities
- 15 edges to [[_COMMUNITY_Agent Base Infrastructure]]
- 14 edges to [[_COMMUNITY_Guardian Risk Layer]]
- 10 edges to [[_COMMUNITY_Trade Execution Engine]]
- 8 edges to [[_COMMUNITY_Commander Orchestration]]
- 4 edges to [[_COMMUNITY_Strategy Architect]]
- 2 edges to [[_COMMUNITY_Agent REST API]]
- 1 edge to [[_COMMUNITY_Strategy & Alert System]]
- 1 edge to [[_COMMUNITY_Terminal Interface]]

## Top bridge nodes
- [[AgentID]] - degree 20, connects to 5 communities
- [[AtlasMessage]] - degree 19, connects to 5 communities
- [[MessageType]] - degree 18, connects to 5 communities
- [[Trader — Order execution agent.]] - degree 17, connects to 5 communities
- [[AgentState]] - degree 11, connects to 2 communities