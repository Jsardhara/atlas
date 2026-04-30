---
source_file: "agents/trader/agent.py"
type: "code"
community: "API Config & Dependencies"
location: "async def _execute_trade"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# TraderAgent._execute_trade

## Connections
- [[KrakenExecutor.execute_trade]] - `calls` [EXTRACTED]
- [[KrakenExecutor.size_position]] - `calls` [EXTRACTED]
- [[Redis Stream atlasevents (message bus)]] - `calls` [EXTRACTED]
- [[TraderAgent.process_message]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies