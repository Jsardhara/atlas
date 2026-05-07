---
source_file: "C:\Users\jyot2\atlas\agents\trader\kraken_executor.py"
type: "rationale"
community: "Trade Execution Engine"
location: "L28"
tags:
  - graphify/rationale
  - graphify/INFERRED
  - community/Trade_Execution_Engine
---

# Calculate position size using Kelly criterion + risk limits.

## Connections
- [[.size_position()]] - `rationale_for` [EXTRACTED]
- [[KrakenClient]] - `uses` [INFERRED]
- [[Settings]] - `uses` [INFERRED]

#graphify/rationale #graphify/INFERRED #community/Trade_Execution_Engine