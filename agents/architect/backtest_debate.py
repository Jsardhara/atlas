"""Backtest harness for the Tauric-replacement debate module.

Replays ``oracle.data_sources.debate.fetch_debate_signal`` against
historical OHLC and scores the debate's BUY/SELL/HOLD calls vs the
realised N-day forward return on each ticker.

Goal: answer the question "is the bull/bear/judge debate any better
than a coin flip" before flipping live trading on. Output is a JSON
summary + an HTML report under ``state/backtests/``.

Heavy: every (ticker, trade_date) pair triggers three Claude Code
subscription calls (bull, bear, judge). Default sample is small —
5 tickers × 14 days × 3 calls ≈ 210 LLM calls. Tune ``tickers`` /
``lookback_days`` per the daily message-quota envelope.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN")
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_FORWARD_BARS = 5  # ~ one trading week at daily bars
DEFAULT_INTERVAL_MINUTES = 1440  # daily

REPORT_DIR = Path("state/backtests")


@dataclass(frozen=True)
class TradeOutcome:
    ticker: str
    trade_date: str
    decision: str  # BUY | SELL | HOLD
    winner: str  # bull | bear | neutral
    conviction: float
    entry_price: float
    forward_price: float
    forward_return_pct: float  # signed: + good for BUY, - good for SELL
    correct: bool  # decision aligned with realised direction


@dataclass
class BacktestSummary:
    total_signals: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    hold_signals: int = 0
    correct_buys: int = 0
    correct_sells: int = 0
    hit_rate: float = 0.0
    avg_return_when_correct: float = 0.0
    avg_return_when_wrong: float = 0.0
    sharpe_like: float = 0.0  # mean / stddev of per-trade returns
    by_ticker: dict[str, dict[str, Any]] = field(default_factory=dict)
    sample_outcomes: list[dict[str, Any]] = field(default_factory=list)


def _trade_dates(lookback_days: int) -> list[str]:
    """Last ``lookback_days`` UTC dates as YYYY-MM-DD strings (newest first)."""
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(1, lookback_days + 1)]


def _close_at(bars: list[list[float]], ts_unix: int) -> float | None:
    """Return the close price of the bar nearest to (and not before) ts_unix."""
    if not bars:
        return None
    for bar in bars:
        if bar[0] >= ts_unix:
            return float(bar[4])
    return None


def _bar_index_at_or_after(bars: list[list[float]], ts_unix: int) -> int | None:
    for idx, bar in enumerate(bars):
        if bar[0] >= ts_unix:
            return idx
    return None


def _score_outcome(
    decision: str,
    entry_price: float,
    forward_price: float,
) -> tuple[float, bool]:
    """Return (forward_return_pct, correct).

    ``correct`` for BUY: forward_price > entry. For SELL: forward_price < entry.
    HOLD never scores correct (informationless from a P&L lens).
    """
    if entry_price <= 0:
        return 0.0, False
    forward_return_pct = (forward_price - entry_price) / entry_price
    if decision == "BUY":
        return forward_return_pct, forward_return_pct > 0
    if decision == "SELL":
        # SELL P&L is the negative of long return.
        return -forward_return_pct, forward_return_pct < 0
    return forward_return_pct, False


async def _backtest_ticker(
    ticker: str,
    trade_dates: list[str],
    forward_bars: int,
    settings: Any,
    redis: Any | None,
    fetch_ohlc_fn: Any,
    fetch_debate_fn: Any,
) -> list[TradeOutcome]:
    """Walk the lookback window for one ticker. Returns one TradeOutcome per
    successful (decision, forward-price) pair."""
    bars = await fetch_ohlc_fn(ticker, interval=DEFAULT_INTERVAL_MINUTES)
    if not bars:
        logger.warning("[backtest] no bars for %s — skipping", ticker)
        return []

    out: list[TradeOutcome] = []
    for date_str in trade_dates:
        try:
            entry_ts = int(
                datetime.fromisoformat(f"{date_str}T00:00:00+00:00").timestamp()
            )
        except ValueError:
            continue
        entry_idx = _bar_index_at_or_after(bars, entry_ts)
        if entry_idx is None or entry_idx + forward_bars >= len(bars):
            continue

        entry_price = float(bars[entry_idx][4])
        forward_price = float(bars[entry_idx + forward_bars][4])

        debate = await fetch_debate_fn(
            ticker,
            trade_date=date_str,
            settings=settings,
            redis=redis,
            market_context={
                "entry_price": entry_price,
                "snapshot": {"close": entry_price},
            },
        )
        if debate is None:
            continue

        decision = debate.get("decision", "HOLD")
        forward_return, correct = _score_outcome(decision, entry_price, forward_price)
        out.append(
            TradeOutcome(
                ticker=ticker,
                trade_date=date_str,
                decision=decision,
                winner=debate.get("debate_log", {}).get("winner", "neutral"),
                conviction=float(debate.get("conviction") or 0.0),
                entry_price=round(entry_price, 4),
                forward_price=round(forward_price, 4),
                forward_return_pct=round(forward_return, 6),
                correct=correct,
            )
        )
    return out


def _summarise(outcomes: list[TradeOutcome]) -> BacktestSummary:
    summary = BacktestSummary()
    summary.total_signals = len(outcomes)
    if not outcomes:
        return summary

    correct_returns: list[float] = []
    wrong_returns: list[float] = []
    for o in outcomes:
        if o.decision == "BUY":
            summary.buy_signals += 1
            if o.correct:
                summary.correct_buys += 1
        elif o.decision == "SELL":
            summary.sell_signals += 1
            if o.correct:
                summary.correct_sells += 1
        else:
            summary.hold_signals += 1
        if o.decision in ("BUY", "SELL"):
            (correct_returns if o.correct else wrong_returns).append(o.forward_return_pct)

    actionable = summary.buy_signals + summary.sell_signals
    correct = summary.correct_buys + summary.correct_sells
    summary.hit_rate = correct / actionable if actionable else 0.0
    summary.avg_return_when_correct = mean(correct_returns) if correct_returns else 0.0
    summary.avg_return_when_wrong = mean(wrong_returns) if wrong_returns else 0.0

    all_returns = [o.forward_return_pct for o in outcomes if o.decision in ("BUY", "SELL")]
    if len(all_returns) >= 2 and pstdev(all_returns) > 0:
        summary.sharpe_like = mean(all_returns) / pstdev(all_returns)

    by_ticker: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        bucket = by_ticker.setdefault(
            o.ticker,
            {"total": 0, "correct": 0, "buys": 0, "sells": 0, "holds": 0},
        )
        bucket["total"] += 1
        if o.decision == "BUY":
            bucket["buys"] += 1
        elif o.decision == "SELL":
            bucket["sells"] += 1
        else:
            bucket["holds"] += 1
        if o.correct:
            bucket["correct"] += 1
    for ticker, bucket in by_ticker.items():
        actionable = bucket["buys"] + bucket["sells"]
        bucket["hit_rate"] = bucket["correct"] / actionable if actionable else 0.0
    summary.by_ticker = by_ticker

    summary.sample_outcomes = [asdict(o) for o in outcomes[:20]]
    return summary


def _render_html(summary: BacktestSummary, run_id: str) -> str:
    rows = "\n".join(
        f"<tr><td>{t}</td><td>{b['total']}</td><td>{b['buys']}</td>"
        f"<td>{b['sells']}</td><td>{b['holds']}</td><td>{b['correct']}</td>"
        f"<td>{b['hit_rate']:.1%}</td></tr>"
        for t, b in sorted(summary.by_ticker.items())
    )
    sample = "\n".join(
        f"<tr><td>{o['ticker']}</td><td>{o['trade_date']}</td><td>{o['decision']}</td>"
        f"<td>{o['winner']}</td><td>{o['conviction']:.2f}</td>"
        f"<td>{o['entry_price']}</td><td>{o['forward_price']}</td>"
        f"<td>{o['forward_return_pct']:+.2%}</td>"
        f"<td>{'✓' if o['correct'] else '✗'}</td></tr>"
        for o in summary.sample_outcomes
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'>
<title>Debate backtest — {run_id}</title>
<style>
  body {{ font-family: ui-monospace, monospace; padding: 20px; background:#0a0a0a; color:#ddd; }}
  h1, h2 {{ color: #fff; }}
  table {{ border-collapse: collapse; margin-bottom: 24px; }}
  th, td {{ border: 1px solid #333; padding: 6px 12px; text-align: right; }}
  th {{ background: #1a1a1a; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .metric {{ font-size: 1.4em; margin-right: 24px; }}
  .good {{ color: #6f9; }}
  .bad {{ color: #f66; }}
</style></head>
<body>
<h1>Debate backtest — {run_id}</h1>
<div>
  <span class='metric'>signals: {summary.total_signals}</span>
  <span class='metric'>actionable: {summary.buy_signals + summary.sell_signals}</span>
  <span class='metric {"good" if summary.hit_rate >= 0.5 else "bad"}'>hit rate: {summary.hit_rate:.1%}</span>
  <span class='metric'>sharpe-like: {summary.sharpe_like:+.3f}</span>
</div>

<h2>Per ticker</h2>
<table>
  <thead><tr><th>ticker</th><th>total</th><th>buys</th><th>sells</th><th>holds</th><th>correct</th><th>hit rate</th></tr></thead>
  <tbody>{rows}</tbody>
</table>

<h2>Sample outcomes (first 20)</h2>
<table>
  <thead><tr><th>ticker</th><th>date</th><th>decision</th><th>winner</th><th>conv</th>
  <th>entry</th><th>+{DEFAULT_FORWARD_BARS}d</th><th>fwd return</th><th>✓/✗</th></tr></thead>
  <tbody>{sample}</tbody>
</table>
</body></html>"""


async def run_debate_backtest(
    *,
    tickers: tuple[str, ...] | list[str] = DEFAULT_TICKERS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forward_bars: int = DEFAULT_FORWARD_BARS,
    settings: Any = None,
    redis: Any | None = None,
    fetch_ohlc_fn: Any = None,
    fetch_debate_fn: Any = None,
    out_dir: Path | str = REPORT_DIR,
) -> dict[str, Any]:
    """Top-level entrypoint. Returns the summary dict + writes JSON + HTML.

    Inject ``fetch_ohlc_fn`` / ``fetch_debate_fn`` for tests.
    """
    if fetch_ohlc_fn is None:
        from oracle.data_sources.alpaca_market import (  # type: ignore[import-not-found]
            fetch_ohlc as _fetch_ohlc,
        )
        fetch_ohlc_fn = _fetch_ohlc
    if fetch_debate_fn is None:
        from oracle.data_sources.debate import (  # type: ignore[import-not-found]
            fetch_debate_signal as _fetch_debate,
        )
        fetch_debate_fn = _fetch_debate
    if settings is None:
        from shared.config import get_settings  # type: ignore[import-not-found]
        settings = get_settings()

    trade_dates = _trade_dates(lookback_days)
    logger.info(
        "[backtest] %d tickers × %d days = up to %d signals",
        len(tickers), lookback_days, len(tickers) * lookback_days,
    )

    outcomes: list[TradeOutcome] = []
    for ticker in tickers:
        result = await _backtest_ticker(
            ticker, trade_dates, forward_bars,
            settings=settings, redis=redis,
            fetch_ohlc_fn=fetch_ohlc_fn,
            fetch_debate_fn=fetch_debate_fn,
        )
        outcomes.extend(result)

    summary = _summarise(outcomes)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = out_path / f"debate_{run_id}.json"
    html_path = out_path / f"debate_{run_id}.html"
    summary_dict = {
        "run_id": run_id,
        "tickers": list(tickers),
        "lookback_days": lookback_days,
        "forward_bars": forward_bars,
        "summary": asdict(summary),
        "outcomes": [asdict(o) for o in outcomes],
    }
    json_path.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")
    html_path.write_text(_render_html(summary, run_id), encoding="utf-8")
    logger.info(
        "[backtest] %d signals, hit_rate=%.1f%%, sharpe-like=%+.3f → %s",
        summary.total_signals, summary.hit_rate * 100, summary.sharpe_like, html_path,
    )
    return summary_dict


def main_cli() -> None:  # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description="Replay debate.py against historical bars")
    p.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--forward-bars", type=int, default=DEFAULT_FORWARD_BARS)
    p.add_argument("--out-dir", default=str(REPORT_DIR))
    args = p.parse_args()

    asyncio.run(
        run_debate_backtest(
            tickers=tuple(args.tickers),
            lookback_days=args.lookback_days,
            forward_bars=args.forward_bars,
            out_dir=args.out_dir,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    main_cli()


__all__ = [
    "BacktestSummary",
    "TradeOutcome",
    "run_debate_backtest",
    "DEFAULT_TICKERS",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_FORWARD_BARS",
]
