"""Tests for ``api/middleware/bearer_auth.py``."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middleware.bearer_auth import _extract_token, verify_bearer_token


# ── unit: header parser ───────────────────────────────────────────────────


def test_extract_token_handles_bearer_prefix() -> None:
    assert _extract_token("Bearer abc123") == "abc123"


def test_extract_token_returns_none_for_missing_header() -> None:
    assert _extract_token(None) is None


def test_extract_token_returns_none_for_wrong_scheme() -> None:
    assert _extract_token("Basic foo") is None


def test_extract_token_returns_none_for_empty_value() -> None:
    assert _extract_token("Bearer ") is None


# ── unit: dependency function ────────────────────────────────────────────


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_dev_mode_bypass_when_token_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty configured token disables auth entirely."""
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = ""

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    # No exception ⇒ pass.
    _run(verify_bearer_token(authorization=None))


def test_rejects_when_header_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = "secret-x"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    with pytest.raises(HTTPException) as ei:
        _run(verify_bearer_token(authorization=None))
    assert ei.value.status_code == 401
    assert ei.value.detail == "missing_or_invalid_bearer"


def test_rejects_when_token_mismatched(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = "secret-x"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    with pytest.raises(HTTPException) as ei:
        _run(verify_bearer_token(authorization="Bearer wrong"))
    assert ei.value.status_code == 401


def test_accepts_when_token_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = "secret-x"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    _run(verify_bearer_token(authorization="Bearer secret-x"))


# ── integration: protects a route ─────────────────────────────────────────


def _make_protected_app() -> FastAPI:
    from fastapi import Depends

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(verify_bearer_token)])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_route_returns_401_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = "abc"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    client = TestClient(_make_protected_app())
    res = client.get("/protected")
    assert res.status_code == 401
    assert res.json()["detail"] == "missing_or_invalid_bearer"


def test_route_returns_200_with_valid_header(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.middleware import bearer_auth

    class _Settings:
        atlas_bearer_token = "abc"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _Settings())
    client = TestClient(_make_protected_app())
    res = client.get("/protected", headers={"Authorization": "Bearer abc"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
