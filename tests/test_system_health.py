"""Tests for ``api/routers/system.py`` health endpoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import dependencies
from api.routers import system as system_router
from tests._fakes import FakeRedis


class _Row:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    def __init__(self, *, agents=None, raise_select=False):
        self._agents = agents or []
        self._raise = raise_select

    async def execute(self, stmt, params=None):
        sql = str(stmt).lower()
        if "select 1" in sql:
            if self._raise:
                raise RuntimeError("db down")
            return _Result([])
        if "from agents" in sql:
            return _Result(self._agents)
        return _Result([])


def _patch_get_db(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    @asynccontextmanager
    async def _fake_get_db(_request):
        yield session

    monkeypatch.setattr(dependencies, "get_db", _fake_get_db)
    monkeypatch.setattr(system_router, "get_db", _fake_get_db)


def _make_app(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.include_router(system_router.router)
    return app


def _fresh_hb() -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(seconds=5)


def _stale_hb() -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(minutes=5)


def test_health_returns_200_when_all_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _Session(
        agents=[
            _Row(id="oracle", state="running", last_heartbeat=_fresh_hb()),
            _Row(id="guardian", state="running", last_heartbeat=_fresh_hb()),
        ]
    )
    _patch_get_db(monkeypatch, sess)
    client = TestClient(_make_app(FakeRedis()))
    res = client.get("/system/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"


def test_health_returns_503_when_agent_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _Session(
        agents=[
            _Row(id="oracle", state="running", last_heartbeat=_stale_hb()),
        ]
    )
    _patch_get_db(monkeypatch, sess)
    client = TestClient(_make_app(FakeRedis()))
    res = client.get("/system/health")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert "oracle" in body["stale_agents"]


def test_health_returns_503_when_agent_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _Session(
        agents=[
            _Row(id="oracle", state="paused", last_heartbeat=_fresh_hb()),
        ]
    )
    _patch_get_db(monkeypatch, sess)
    client = TestClient(_make_app(FakeRedis()))
    res = client.get("/system/health")
    assert res.status_code == 503
    body = res.json()
    assert body["agents"]["oracle"]["state"] == "paused"


def test_health_returns_503_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _Session(raise_select=True)
    _patch_get_db(monkeypatch, sess)
    client = TestClient(_make_app(FakeRedis()))
    res = client.get("/system/health")
    assert res.status_code == 503
    assert "error" in res.json()["postgres"]


def test_health_returns_503_when_redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    sess = _Session(
        agents=[_Row(id="oracle", state="running", last_heartbeat=_fresh_hb())]
    )
    _patch_get_db(monkeypatch, sess)

    class _BrokenRedis(FakeRedis):
        async def ping(self) -> bool:
            raise RuntimeError("redis down")

    client = TestClient(_make_app(_BrokenRedis()))
    res = client.get("/system/health")
    assert res.status_code == 503
    assert "error" in res.json()["redis"]
