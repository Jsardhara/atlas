"""Run Freqtrade backtests via Docker SDK."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STRATEGIES_PATH = Path("/freqtrade/user_data/strategies")
RESULTS_PATH = Path("/freqtrade/user_data/backtest_results")


async def run_backtest(strategy_name: str, timerange: str = "20240101-") -> dict:
    try:
        import docker
        client = docker.from_env()
        RESULTS_PATH.mkdir(parents=True, exist_ok=True)

        output = client.containers.run(
            image="freqtradeorg/freqtrade:stable",
            command=(
                f"backtesting "
                f"--config /freqtrade/user_data/config.json "
                f"--strategy {strategy_name} "
                f"--timerange {timerange} "
                f"--export trades "
                f"--export-filename /freqtrade/user_data/backtest_results/{strategy_name}.json "
                f"--cache none"
            ),
            volumes={
                "atlas_userdata": {"bind": "/freqtrade/user_data", "mode": "rw"},
            },
            network="atlas_network",
            remove=True,
            stdout=True,
            stderr=True,
        )
        logger.info("[Architect] Backtest output: %s", output.decode()[-500:])

        results_file = RESULTS_PATH / f"{strategy_name}.json"
        if results_file.exists():
            with open(results_file) as f:
                return json.load(f)
        return {"error": "Results file not found"}
    except Exception as e:
        logger.error("[Architect] Backtest failed: %s", e)
        return {"error": str(e)}


def score_backtest(results: dict) -> dict:
    """Extract key metrics from Freqtrade backtest JSON."""
    try:
        summary = results.get("strategy", {})
        if not summary:
            return {"error": "No strategy summary in results"}

        strat = next(iter(summary.values()), {})
        return {
            "total_trades": strat.get("total_trades", 0),
            "win_rate": strat.get("wins", 0) / max(strat.get("total_trades", 1), 1),
            "profit_total_pct": strat.get("profit_total", 0),
            "max_drawdown": strat.get("max_drawdown", 0),
            "sharpe_ratio": strat.get("sharpe", 0),
            "profit_factor": strat.get("profit_factor", 0),
            "avg_profit_pct": strat.get("profit_mean", 0),
            "duration_avg": strat.get("holding_avg", "N/A"),
        }
    except Exception as e:
        return {"error": str(e)}
