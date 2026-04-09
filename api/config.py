from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://atlas:atlas_secure_pw_2026@postgres:5432/atlas"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret_key: str = "change_me"
    api_admin_password: str = "atlas_admin_2026"
    environment: str = "development"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
