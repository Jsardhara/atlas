"""Atlas runtime settings.

LLM auth is handled by the Claude Agent SDK via the host's ``~/.claude/``
session — there is no Anthropic API key in this file. ``ATLAS_BEARER_TOKEN``
is the shared secret between Jarvis and the Atlas API surface.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Claude model routing (per-agent). Auth is via Claude Code subscription;
    # no API key field. See agents/shared/claude_client.py.
    agent_oracle_model: str = "claude-sonnet-4-6"
    agent_architect_model: str = "claude-opus-4-7"
    agent_guardian_model: str = "claude-haiku-4-5"
    agent_trader_model: str = "claude-sonnet-4-6"
    agent_sage_model: str = "claude-haiku-4-5"

    # Jarvis ↔ Atlas auth
    atlas_bearer_token: str = ""

    # Alpaca (broker)
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"  # iex | sip — sip needs paid subscription

    # Database
    database_url: str = "postgresql+asyncpg://atlas:atlas_secure_pw_2026@postgres:5432/atlas"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Trading safety
    live_trading_enabled: bool = False
    max_leverage: int = 5
    daily_loss_limit_usd: float = 50.0
    max_portfolio_risk_pct: float = 0.10

    # External APIs
    cryptopanic_api_key: str = ""
    glassnode_api_key: str = ""
    fred_api_key: str = ""

    # Native bull/bear/judge debate (replaces Tauric — runs on Claude Code subscription)
    debate_enabled: bool = True
    debate_analyst_model: str = "claude-sonnet-4-6"
    debate_judge_model: str = "claude-opus-4-7"
    debate_top_n: int = 3  # only debate the top N screener candidates per cycle
    debate_daily_budget_usd: float = 5.0  # informational cap (subscription-billed)
    debate_per_call_budget_usd: float = 0.50  # per-ticker estimated ceiling

    # Universe whitelist — caps the screener to a known-liquid subset so
    # scoring 12k+ Alpaca assets doesn't take hours. Comma-separated symbols
    # (equities + crypto pairs). Empty value = no cap (legacy behavior).
    atlas_universe_whitelist: str = (
        "AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AVGO,JPM,V,"
        "UNH,XOM,LLY,WMT,MA,PG,JNJ,HD,COST,ORCL,"
        "ABBV,BAC,KO,MRK,CVX,PEP,ADBE,CSCO,NFLX,CRM,"
        "AMD,WFC,TMO,LIN,ACN,DIS,MCD,ABT,DHR,VZ,"
        "PM,CMCSA,IBM,GE,QCOM,INTU,T,AXP,UBER,GS,"
        "BTC/USD,ETH/USD,SOL/USD"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
