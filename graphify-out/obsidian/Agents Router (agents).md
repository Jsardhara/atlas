---
source_file: "api/routers/agents.py"
type: "code"
community: "API Config & Dependencies"
location: "router = APIRouter prefix=/agents"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/API_Config_&_Dependencies
---

# Agents Router (/agents)

## Connections
- [[ATLAS FastAPI App Instance]] - `references` [EXTRACTED]
- [[DB Table agents]] - `shares_data_with` [EXTRACTED]
- [[DB Table chat_messages]] - `shares_data_with` [EXTRACTED]
- [[get_db (async session context manager)]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/API_Config_&_Dependencies