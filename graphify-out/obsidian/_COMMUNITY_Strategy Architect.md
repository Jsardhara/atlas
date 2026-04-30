---
type: community
cohesion: 0.27
members: 10
---

# Strategy Architect

**Cohesion:** 0.27 - loosely connected
**Members:** 10 nodes

## Members
- [[._generation_cycle()]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[._on_chat()]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[._run_loop()]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[.process_message()]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[ArchitectAgent]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[Extract key metrics from Freqtrade backtest JSON.]] - rationale - C:\Users\jyot2\atlas\agents\architect\backtest_runner.py
- [[Run Freqtrade backtests via Docker SDK.]] - rationale - C:\Users\jyot2\atlas\agents\architect\backtest_runner.py
- [[agent.py]] - code - C:\Users\jyot2\atlas\agents\architect\agent.py
- [[backtest_runner.py]] - code - C:\Users\jyot2\atlas\agents\architect\backtest_runner.py
- [[score_backtest()]] - code - C:\Users\jyot2\atlas\agents\architect\backtest_runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Strategy_Architect
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Agent Protocol Layer]]
- 3 edges to [[_COMMUNITY_Guardian Risk Layer]]
- 2 edges to [[_COMMUNITY_Strategy & Alert System]]
- 1 edge to [[_COMMUNITY_Agent Base Infrastructure]]

## Top bridge nodes
- [[ArchitectAgent]] - degree 11, connects to 3 communities
- [[agent.py]] - degree 4, connects to 2 communities
- [[backtest_runner.py]] - degree 4, connects to 1 community
- [[score_backtest()]] - degree 3, connects to 1 community