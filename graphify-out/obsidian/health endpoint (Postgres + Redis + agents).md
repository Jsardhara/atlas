---
source_file: "api/routers/system.py"
type: "code"
community: "API Config & Dependencies"
location: "async def health"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# health endpoint (Postgres + Redis + agents)

## Connections
- [[DB Table agents]] - `shares_data_with` [EXTRACTED]
- [[get_db (async session context manager)]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies