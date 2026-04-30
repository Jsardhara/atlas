---
source_file: "agents/trader/kraken_executor.py"
type: "code"
community: "Trade Execution Engine"
location: "async def size_position"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Trade_Execution_Engine
---

# KrakenExecutor.size_position

## Connections
- [[DB Table portfolio_snapshots]] - `shares_data_with` [EXTRACTED]
- [[DB Table trades]] - `shares_data_with` [EXTRACTED]
- [[Kelly Criterion Position Sizing]] - `implements` [EXTRACTED]
- [[TraderAgent._execute_trade]] - `calls` [EXTRACTED]
- [[kelly_fraction()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Trade_Execution_Engine