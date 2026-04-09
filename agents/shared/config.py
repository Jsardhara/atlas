from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenRouter
    openrouter_api_key: str
    agent_commander_model: str = "deepseek/deepseek-r1:free"
    agent_oracle_model: str = "google/gemini-2.0-flash-exp:free"
    agent_guardian_model: str = "deepseek/deepseek-r1:free"
    agent_trader_model: str = "google/gemini-flash-1.5-8b:free"
    agent_sage_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    agent_architect_model: str = "qwen/qwen-2.5-coder-32b-instruct:free"

    # Kraken
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
    commander_alert_threshold: float = 0.05

    # External APIs
    cryptopanic_api_key: str = ""
    glassnode_api_key: str = ""
    fred_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
