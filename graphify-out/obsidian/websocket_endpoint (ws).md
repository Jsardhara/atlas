---
source_file: "api/websocket/router.py"
type: "code"
community: "API Config & Dependencies"
location: "async def websocket_endpoint"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# websocket_endpoint (/ws)

## Connections
- [[ATLAS FastAPI App Instance]] - `references` [EXTRACTED]
- [[ConnectionManager (WebSocket broadcast)]] - `calls` [EXTRACTED]
- [[Next.js Config (ATLAS Dashboard)]] - `references` [EXTRACTED]
- [[Redis Stream atlasevents (message bus)]] - `calls` [EXTRACTED]
- [[WebSocket-Redis Bridge Pattern]] - `implements` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies