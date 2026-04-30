"""Tests for ``api/middleware/idempotency.py``."""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from api.middleware.idempotency import (
    IdempotencyDecision,
    _is_uuid_shaped,
    idempotency_check,
    store_idempotent_response,
)
from tests._fakes import FakeRedis


def test_uuid_validator_accepts_uuid() -> None:
    assert _is_uuid_shaped(str(uuid.uuid4())) is True


def test_uuid_validator_rejects_garbage() -> None:
    assert _is_uuid_shaped("not-a-uuid") is False


def _make_app(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis

    @app.post("/echo")
    async def echo(
        request: Request,
        decision: IdempotencyDecision = Depends(idempotency_check),
    ) -> dict:
        if decision.is_hit:
            return decision.cached_body
        body = {"value": "fresh"}
        await store_idempotent_response(request, decision, body, status_code=200)
        return body

    return app


def test_first_request_passes_through_no_key() -> None:
    redis = FakeRedis()
    client = TestClient(_make_app(redis))
    res = client.post("/echo")
    assert res.status_code == 200
    assert res.json() == {"value": "fresh"}


def test_first_request_with_key_caches_response() -> None:
    redis = FakeRedis()
    client = TestClient(_make_app(redis))
    key = str(uuid.uuid4())
    res1 = client.post("/echo", headers={"X-Idempotency-Key": key})
    assert res1.status_code == 200
    res2 = client.post("/echo", headers={"X-Idempotency-Key": key})
    assert res2.status_code == 200
    assert res2.json() == res1.json()


def test_distinct_keys_do_not_dedup() -> None:
    redis = FakeRedis()
    client = TestClient(_make_app(redis))
    res1 = client.post("/echo", headers={"X-Idempotency-Key": str(uuid.uuid4())})
    res2 = client.post("/echo", headers={"X-Idempotency-Key": str(uuid.uuid4())})
    assert res1.status_code == 200
    assert res2.status_code == 200


def test_invalid_key_shape_falls_through_no_dedup() -> None:
    redis = FakeRedis()
    client = TestClient(_make_app(redis))
    # Invalid keys are silently treated as no-key — must not 500.
    res = client.post("/echo", headers={"X-Idempotency-Key": "not-a-uuid"})
    assert res.status_code == 200


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """After the dedup window passes, the next request should re-execute."""
    redis = FakeRedis()
    app = _make_app(redis)
    client = TestClient(app)
    key = str(uuid.uuid4())
    client.post("/echo", headers={"X-Idempotency-Key": key})
    # Force expiry by mutating the entry's ttl to 0s.
    rkey = f"idem:{key}"
    value, _ = redis._kv[rkey]
    redis._kv[rkey] = (value, 0.0)
    # Second call should now be a miss → fresh execution.
    res = client.post("/echo", headers={"X-Idempotency-Key": key})
    assert res.status_code == 200
    assert res.json() == {"value": "fresh"}


def test_store_response_is_noop_without_key() -> None:
    """``store_idempotent_response`` should silently skip when there is no key."""
    redis = FakeRedis()

    async def _go() -> None:
        request = type(
            "Req",
            (),
            {"app": type("App", (), {"state": type("S", (), {"redis": redis})()})()},
        )
        decision = IdempotencyDecision(key=None)
        await store_idempotent_response(request, decision, {"x": 1})  # type: ignore[arg-type]
        assert redis._kv == {}

    _run(_go())


def test_corrupted_cache_entry_does_not_crash() -> None:
    redis = FakeRedis()
    app = _make_app(redis)
    client = TestClient(app)
    key = str(uuid.uuid4())
    # Pre-populate a bad payload directly.
    _run(redis.set(f"idem:{key}", "not json", ex=60))
    res = client.post("/echo", headers={"X-Idempotency-Key": key})
    # Corrupt cache → falls through, never 500.
    assert res.status_code == 200
    assert res.json() == {"value": "fresh"}


def test_envelope_status_code_is_replayed() -> None:
    """A non-200 cached status should be returned on replay."""
    redis = FakeRedis()
    key = str(uuid.uuid4())
    _run(
        redis.set(
            f"idem:{key}",
            json.dumps({"status_code": 202, "body": {"queued": True}}),
            ex=60,
        )
    )
    app = _make_app(redis)
    client = TestClient(app)
    res = client.post("/echo", headers={"X-Idempotency-Key": key})
    assert res.status_code == 202
    assert res.json() == {"queued": True}
