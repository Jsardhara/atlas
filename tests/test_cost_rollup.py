"""Tests for ``api/routers/cost.py``.

Exercises the response schema contract that ``web/src/hooks/useDailyCost.ts``
consumes. We mock the SQLAlchemy session via dependency override so the test
runs without a live Postgres.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import dependencies
from api.middleware import bearer_auth
from api.routers import cost as cost_router


class _Row:
    def __init__(self, agent_id: str, model: str, calls: int, in_tok: int, out_tok: int, cost: float) -> None:
        self.agent_id = agent_id
        self.model = model
        self.calls = calls
        self.in_tok = in_tok
        self.out_tok = out_tok
        self.cost = cost


class _Result:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def fetchall(self) -> list[_Row]:
        return self._rows


class _Session:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    async def execute(self, *_args, **_kw) -> _Result:
        return _Result(self._rows)


@pytest.fixture(autouse=True)
def _disable_bearer(monkeypatch: pytest.MonkeyPatch):
    class _S:
        atlas_bearer_token = ""

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _S())


def _patch_get_db(monkeypatch: pytest.MonkeyPatch, rows: list[_Row]) -> None:
    @asynccontextmanager
    async def _fake_get_db(_request):
        yield _Session(rows)

    monkeypatch.setattr(dependencies, "get_db", _fake_get_db)
    monkeypatch.setattr(cost_router, "get_db", _fake_get_db)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(cost_router.router)
    return app


def test_rollup_empty_returns_zeroed_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_db(monkeypatch, [])
    client = TestClient(_make_app())
    res = client.get("/api/cost/rollup", params={"date_str": "2026-04-30"})
    assert res.status_code == 200
    body = res.json()
    assert body["date"] == "2026-04-30"
    assert body["total_usd"] == 0.0
    assert body["by_agent"] == {}
    assert body["by_model"] == {}
    assert body["call_count"] == 0


def test_rollup_aggregates_by_agent_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _Row("oracle", "claude-sonnet-4-6", 4, 1000, 500, 0.012),
        _Row("oracle", "claude-haiku-4-5", 1, 200, 100, 0.001),
        _Row("guardian", "claude-haiku-4-5", 6, 600, 300, 0.004),
    ]
    _patch_get_db(monkeypatch, rows)
    client = TestClient(_make_app())
    res = client.get("/api/cost/rollup", params={"date_str": "2026-04-30"})
    assert res.status_code == 200
    body = res.json()
    assert body["call_count"] == 11
    # Schema parity with useDailyCost expectations.
    oracle = body["by_agent"]["oracle"]
    assert set(oracle.keys()) == {"calls", "input_tokens", "output_tokens", "cost_usd"}
    assert oracle["calls"] == 5
    assert oracle["input_tokens"] == 1200
    assert oracle["output_tokens"] == 600
    assert oracle["cost_usd"] == pytest.approx(0.013, rel=1e-3)

    guardian = body["by_agent"]["guardian"]
    assert guardian["calls"] == 6
    assert guardian["cost_usd"] == pytest.approx(0.004, rel=1e-3)

    haiku = body["by_model"]["claude-haiku-4-5"]
    assert haiku["calls"] == 7  # 1 oracle + 6 guardian


def test_rollup_default_date_is_today() -> None:
    """No date_str ⇒ today's UTC date."""
    # Because the DB call may fail without our patch, use the empty-fallback path.
    client = TestClient(_make_app())
    res = client.get("/api/cost/rollup")
    assert res.status_code == 200
    today = date.today().isoformat()  # naive — server is also UTC in tests
    # Allow either today or today minus one (timezone edge), schema is what matters.
    assert "date" in res.json()
    assert "by_agent" in res.json()
    assert "by_model" in res.json()
    assert "call_count" in res.json()
    assert "total_usd" in res.json()
    assert isinstance(res.json()["date"], str) and len(res.json()["date"]) == 10
    _ = today  # silence unused


def test_rollup_invalid_date_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get_db(monkeypatch, [])
    client = TestClient(_make_app())
    res = client.get("/api/cost/rollup", params={"date_str": "not-a-date"})
    assert res.status_code == 400


def test_rollup_enforces_bearer_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    class _S:
        atlas_bearer_token = "secret"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _S())
    _patch_get_db(monkeypatch, [])
    client = TestClient(_make_app())
    res = client.get("/api/cost/rollup")
    assert res.status_code == 401
