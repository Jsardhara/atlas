"""Idempotency dependency — dedupes POSTs within 60 s via Redis.

Clients send a UUID-shaped ``X-Idempotency-Key`` header. The first request
within the dedup window goes through normally; the dependency reserves the key
in Redis (``SET idem:<key> <placeholder> EX 60 NX``). When a route handler
finishes it should call :func:`store_idempotent_response` to persist its
response payload, so subsequent calls within the window receive the cached
JSON envelope and the original status code.

The header is *optional*; if no key is sent, the request flows through
normally with no caching.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Header, Request, Response

_PLACEHOLDER = "__pending__"
_TTL_SECONDS = 60


@dataclass(frozen=True)
class IdempotencyDecision:
    """Outcome of the idempotency check.

    Attributes:
        key: The validated idempotency key, or ``None`` if no header was sent.
        cached_status: HTTP status code from the prior response, if a hit.
        cached_body: Decoded JSON body from the prior response, if a hit.
    """

    key: str | None
    cached_status: int | None = None
    cached_body: Any | None = None

    @property
    def is_hit(self) -> bool:
        return self.cached_status is not None

    @property
    def should_cache(self) -> bool:
        return self.key is not None and not self.is_hit


def _is_uuid_shaped(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _redis_key(key: str) -> str:
    return f"idem:{key}"


async def idempotency_check(
    request: Request,
    response: Response,
    x_idempotency_key: str | None = Header(default=None),
) -> IdempotencyDecision:
    """FastAPI dependency: cache hit replays prior response, miss reserves key.

    On cache hit, the dependency mutates ``response.status_code`` to match the
    cached status so the route can simply return ``decision.cached_body``.
    """
    if not x_idempotency_key:
        return IdempotencyDecision(key=None)

    key = x_idempotency_key.strip()
    if not _is_uuid_shaped(key):
        # Treat malformed keys as no-key — never silently dedup invalid input.
        return IdempotencyDecision(key=None)

    redis = request.app.state.redis
    rkey = _redis_key(key)

    # Atomically reserve the key. NX = only set if absent.
    reserved = await redis.set(rkey, _PLACEHOLDER, ex=_TTL_SECONDS, nx=True)
    if reserved:
        return IdempotencyDecision(key=key)

    cached_raw = await redis.get(rkey)
    if cached_raw is None or cached_raw == _PLACEHOLDER:
        # Key is reserved but the previous request hasn't finished writing.
        # Safest: treat as miss but don't cache (avoid double-write).
        return IdempotencyDecision(key=None)

    try:
        envelope = json.loads(cached_raw)
        status_code = int(envelope.get("status_code", 200))
        body = envelope.get("body")
    except (ValueError, TypeError):
        return IdempotencyDecision(key=None)

    response.status_code = status_code
    return IdempotencyDecision(
        key=key,
        cached_status=status_code,
        cached_body=body,
    )


async def store_idempotent_response(
    request: Request,
    decision: IdempotencyDecision,
    body: Any,
    status_code: int = 200,
) -> None:
    """Persist a response envelope under the idempotency key (if any)."""
    if not decision.should_cache or decision.key is None:
        return
    redis = request.app.state.redis
    envelope = json.dumps({"status_code": status_code, "body": body})
    await redis.set(_redis_key(decision.key), envelope, ex=_TTL_SECONDS)


__all__ = [
    "IdempotencyDecision",
    "idempotency_check",
    "store_idempotent_response",
]
