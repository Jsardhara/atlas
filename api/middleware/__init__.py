"""FastAPI middleware/dependencies for the Atlas API surface.

Currently provides:
* :mod:`bearer_auth` — shared-secret bearer token verification used between
  Jarvis and Atlas.
* :mod:`idempotency` — Redis-backed dedup of POST requests within a 60-second
  window keyed by ``X-Idempotency-Key``.
"""

from .bearer_auth import verify_bearer_token
from .idempotency import IdempotencyDecision, idempotency_check

__all__ = [
    "IdempotencyDecision",
    "idempotency_check",
    "verify_bearer_token",
]
