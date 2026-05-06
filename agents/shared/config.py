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

    # Kraken (deprecated — kept for migration window so old WIP still imports)
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    kraken_use_demo: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://atlas:atlas_secure_pw_2026@postgres:5432/atlas"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Freqtrade
    freqtrade_url: str = "http://freqtrade:8080"
    freqtrade_username: str = "freqtrader"
    freqtrade_password: str = "SuperSecret1!"

    # Trading safety
    live_trading_enabled: bool = False
    max_leverage: int = 5
    daily_loss_limit_usd: float = 50.0
    max_portfolio_risk_pct: float = 0.10

    # External APIs
    cryptopanic_api_key: str = ""
    glassnode_api_key: str = ""
    fred_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
