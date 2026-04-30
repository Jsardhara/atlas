"""Bearer-token auth dependency for Atlas API routes.

Compares the ``Authorization: Bearer <token>`` header against
``settings.atlas_bearer_token`` using :func:`secrets.compare_digest` to avoid
timing leaks. An empty configured token disables auth (dev mode).
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

# `agents/shared/config.py` is the canonical settings module — same one the
# pipeline orchestrator consumes — so token rotations stay coherent.
from shared.config import get_settings  # type: ignore[import-not-found]


_BEARER_PREFIX = "Bearer "


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith(_BEARER_PREFIX):
        return None
    return authorization[len(_BEARER_PREFIX) :].strip() or None


async def verify_bearer_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Reject the request unless ``Authorization: Bearer <token>`` matches.

    When ``atlas_bearer_token`` is empty, auth is disabled (dev/local mode).
    """
    expected = get_settings().atlas_bearer_token
    if not expected:
        return  # dev-mode bypass

    token = _extract_token(authorization)
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_or_invalid_bearer",
        )


__all__ = ["verify_bearer_token"]
