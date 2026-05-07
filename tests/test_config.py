"""Verify Settings defaults align with the Claude-SDK swap (plan Phase 1)."""
from __future__ import annotations

from shared.config import Settings


def test_oracle_model_default_is_sonnet() -> None:
    # Arrange / Act
    settings = Settings()

    # Assert
    assert settings.agent_oracle_model == "claude-sonnet-4-6"


def test_architect_model_default_is_opus() -> None:
    settings = Settings()
    assert settings.agent_architect_model == "claude-opus-4-7"


def test_guardian_model_default_is_haiku() -> None:
    settings = Settings()
    assert settings.agent_guardian_model == "claude-haiku-4-5"


def test_trader_model_default_is_sonnet() -> None:
    settings = Settings()
    assert settings.agent_trader_model == "claude-sonnet-4-6"


def test_sage_model_default_is_haiku() -> None:
    settings = Settings()
    assert settings.agent_sage_model == "claude-haiku-4-5"


def test_atlas_bearer_token_field_exists() -> None:
    """Bearer-token field is present (default empty, populated via env on first run)."""
    settings = Settings()
    assert hasattr(settings, "atlas_bearer_token")
    assert isinstance(settings.atlas_bearer_token, str)


def test_commander_settings_removed() -> None:
    """Commander knobs must be gone — no lingering config surface."""
    settings = Settings()
    assert not hasattr(settings, "agent_commander_model")
    assert not hasattr(settings, "commander_alert_threshold")


def test_openrouter_api_key_removed() -> None:
    """OpenRouter is no longer the LLM provider — field must not exist."""
    settings = Settings()
    assert not hasattr(settings, "openrouter_api_key")


def test_max_leverage_preserved() -> None:
    """Trading safety knobs unchanged by the LLM swap.

    Pass ``_env_file=None`` so the test asserts hard-coded defaults rather
    than whatever the operator has in their local ``.env``.
    """
    settings = Settings(_env_file=None)
    assert settings.max_leverage == 5
    assert settings.live_trading_enabled is False
