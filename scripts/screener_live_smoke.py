"""One-shot live screener smoke against the real Kraken public API.

Run: `python scripts/screener_live_smoke.py [TOP_N]`
No API key needed. Used by atlas-trading-engineer for proof-of-life.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
if str(AGENTS) not in sys.path:
    sys.path.insert(0, str(AGENTS))

from oracle.data_sources.kraken_market import discover_universe  # noqa: E402
from oracle.screener import screen_universe  # noqa: E402


async def main(top_n: int = 3, sample_size: int = 25) -> None:
    print(f"[smoke] discovering Kraken USD universe...")
    universe = await discover_universe()
    print(f"[smoke] universe size: {len(universe)} pairs")
    shortable = sum(1 for p in universe if p.shortable)
    print(f"[smoke] shortable: {shortable}")

    # Restrict to first N pairs to respect rate limits
    sample = universe[:sample_size]
    print(f"[smoke] scoring {len(sample)} pairs (rate-limited 1 RPS)...")
    candidates = await screen_universe(sample, top_n=top_n, min_volume_usd_24h=100_000)
    print(f"[smoke] top {len(candidates)} candidates:")
    for c in candidates:
        snap = c.snapshot
        print(
            f"  {c.pair:<12} score={c.score:+.3f}  dir={c.suggested_direction:<7} "
            f"shortable={c.shortable}  close={snap.get('close'):.4f}  "
            f"vol24h_quote={snap.get('volume_24h_quote', 0):,.0f}  [{snap.get('indicators')}]"
        )


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(main(top_n=n))
