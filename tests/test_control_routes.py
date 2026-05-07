"""Tests for ``api/routers/control.py`` — Jarvis decision-layer surface."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import dependencies
from api.middleware import bearer_auth
from api.routers import control as control_router
from tests._fakes import FakeRedis


class _FakeRow:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeResult:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[_FakeRow]:
        return self._rows

    def fetchone(self) -> _FakeRow | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Minimal AsyncSession surrogate. Records statements; returns canned rows
    keyed by SQL substring."""

    def __init__(self, agents: list[_FakeRow] | None = None) -> None:
        self._agents = agents or [
            _FakeRow(
                id="oracle",
                state="running",
                last_heartbeat=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            ),
            _FakeRow(
                id="trader",
                state="running",
                last_heartbeat=None,
            ),
        ]
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(stmt)
        self.statements.append((sql, dict(params or {})))
        if "UPDATE agents SET state" in sql:
            new_state = (params or {}).get("state") or (
                "paused" if "'paused'" in sql else "running"
            )
            for agent in self._agents:
                if agent.id == (params or {}).get("id"):
                    agent.state = new_state
            return _FakeResult([])
        if "SELECT id, state, last_heartbeat FROM agents" in sql:
            return _FakeResult(self._agents)
        return _FakeResult([])

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture(autouse=True)
def _disable_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    class _S:
        atlas_bearer_token = ""

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _S())


@pytest.fixture
def app_redis_session(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FastAPI, FakeRedis, _FakeSession]:
    app = FastAPI()
    redis = FakeRedis()
    session = _FakeSession()
    app.state.redis = redis

    @asynccontextmanager
    async def _fake_get_db(_request: Any):
        yield session

    monkeypatch.setattr(dependencies, "get_db", _fake_get_db)
    monkeypatch.setattr(control_router, "get_db", _fake_get_db)
    app.include_router(control_router.router)
    return app, redis, session


def test_pause_agent_updates_state_and_publishes(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, redis, session = app_redis_session
    client = TestClient(app)
    res = client.post("/control/pause-agent", json={"agent_id": "oracle"})
    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] == "oracle"
    assert body["state"] == "paused"
    assert body["command_id"]
    # DB hit
    assert any("UPDATE agents SET state = 'paused'" in s for s, _ in session.statements)
    assert session.commits == 1
    # Redis stream got the command
    msgs = redis._streams.get("atlas:events", [])
    assert msgs, "expected pause command on the stream"
    payload = json.loads(msgs[0][1]["json"])
    assert payload["target_agent"] == "oracle"
    assert payload["payload"]["command"] == "pause"


def test_resume_agent_updates_state(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, _redis, session = app_redis_session
    client = TestClient(app)
    res = client.post("/control/resume-agent", json={"agent_id": "trader"})
    assert res.status_code == 200
    assert res.json()["state"] == "running"
    assert any(
        "UPDATE agents SET state = 'running'" in s for s, _ in session.statements
    )


def test_pause_agent_rejects_unknown_id(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, _redis, _session = app_redis_session
    client = TestClient(app)
    res = client.post("/control/pause-agent", json={"agent_id": "nonsense"})
    assert res.status_code == 400
    assert "unknown_agent_id" in res.json()["detail"]


def test_list_agent_state(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, _redis, _session = app_redis_session
    client = TestClient(app)
    res = client.get("/control/agent-state")
    assert res.status_code == 200
    body = res.json()
    ids = [a["id"] for a in body["agents"]]
    assert ids == ["oracle", "trader"]


def test_strategy_weights_round_trip(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, _redis, _session = app_redis_session
    client = TestClient(app)
    res = client.post(
        "/control/strategy-weights",
        json={"weights": {"trend_v1": 1.5, "mean_reversion_v3": 0.5}},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 2

    res = client.get("/control/strategy-weights")
    assert res.status_code == 200
    body = res.json()
    assert body["weights"] == {"trend_v1": 1.5, "mean_reversion_v3": 0.5}


def test_strategy_weights_empty_clears(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, _redis, _session = app_redis_session
    client = TestClient(app)
    client.post(
        "/control/strategy-weights", json={"weights": {"trend_v1": 1.5}}
    )
    res = client.post("/control/strategy-weights", json={"weights": {}})
    assert res.status_code == 200
    assert res.json()["weights"] == {}
    res = client.get("/control/strategy-weights")
    assert res.json()["weights"] == {}


def test_oracle_scan_publishes_command(
    app_redis_session: tuple[FastAPI, FakeRedis, _FakeSession],
) -> None:
    app, redis, _session = app_redis_session
    client = TestClient(app)
    res = client.post(
        "/control/oracle-scan",
        json={"reason": "vix-spike", "universe": ["AAPL", "MSFT"]},
    )
    assert res.status_code == 200
    msgs = redis._streams.get("atlas:events", [])
    assert msgs
    payload = json.loads(msgs[0][1]["json"])
    assert payload["target_agent"] == "oracle"
    assert payload["payload"]["command"] == "scan"
    assert payload["payload"]["reason"] == "vix-spike"
    assert payload["payload"]["universe"] == ["AAPL", "MSFT"]


def test_control_routes_enforce_bearer_when_token_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _S:
        atlas_bearer_token = "abc"

    monkeypatch.setattr(bearer_auth, "get_settings", lambda: _S())
    app = FastAPI()
    app.state.redis = FakeRedis()
    app.include_router(control_router.router)
    client = TestClient(app)
    res = client.post("/control/pause-agent", json={"agent_id": "oracle"})
    assert res.status_code == 401
