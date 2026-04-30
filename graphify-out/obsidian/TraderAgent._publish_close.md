---
source_file: "agents/trader/agent.py"
type: "code"
community: "API Config & Dependencies"
location: "async def _publish_close"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# TraderAgent._publish_close

## Connections
- [[DB Table trades]] - `shares_data_with` [EXTRACTED]
- [[Redis Stream atlasevents (message bus)]] - `calls` [EXTRACTED]
- [[TraderAgent._monitor_open_positions]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies