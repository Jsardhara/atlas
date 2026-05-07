---
source_file: "api/main.py"
type: "code"
community: "API Config & Dependencies"
location: "async def lifespan"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# API Lifespan (startup/shutdown)

## Connections
- [[ATLAS FastAPI App Instance]] - `calls` [EXTRACTED]
- [[Redis Stream atlasevents (message bus)]] - `calls` [INFERRED]
- [[get_settings (lru_cache factory)]] - `calls` [EXTRACTED]
- [[init_db (async engine setup)]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies