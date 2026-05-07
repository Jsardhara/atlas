"""Lightweight async fakes used across api tests.

We avoid pulling in ``fakeredis`` so the test surface stays dependency-light;
only the redis-async surface area exercised by the new code is implemented.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


class FakeRedis:
    """Tiny subset of ``redis.asyncio.Redis`` used by api/middleware + orchestrator.

    Implements: ``set(... ex=, nx=)``, ``get``, ``ping``, ``aclose``, plus the
    Streams operations exercised by the orchestrator (``xadd``, ``xread``,
    ``xreadgroup``, ``xack``, ``xgroup_create``).
    """

    def __init__(self) -> None:
        self._kv: dict[str, tuple[str, float | None]] = {}
        # streams: stream_name -> list[(id, fields)]
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._groups: dict[tuple[str, str], dict[str, Any]] = {}
        self._counter = 0
        self._lock = asyncio.Lock()

    # ── kv ────────────────────────────────────────────────────────────────

    def _expired(self, key: str) -> bool:
        entry = self._kv.get(key)
        if entry is None:
            return True
        _, exp = entry
        if exp is None:
            return False
        if exp <= time.monotonic():
            self._kv.pop(key, None)
            return True
        return False

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        async with self._lock:
            if nx and not self._expired(key):
                return False
            exp = time.monotonic() + ex if ex else None
            self._kv[key] = (value, exp)
            return True

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            return None
        return self._kv[key][0]

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            removed = 0
            for k in keys:
                if k in self._kv:
                    del self._kv[k]
                    removed += 1
            return removed

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    # ── streams ───────────────────────────────────────────────────────────

    def _next_id(self) -> str:
        self._counter += 1
        ms = int(time.time() * 1000)
        return f"{ms}-{self._counter}"

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        async with self._lock:
            msg_id = self._next_id()
            self._streams.setdefault(stream, []).append((msg_id, dict(fields)))
            return msg_id

    async def xread(
        self,
        streams: dict[str, str],
        count: int = 10,
        block: int | None = None,
    ) -> list:
        # block is in ms; we poll briefly so tests stay snappy.
        deadline = (
            asyncio.get_event_loop().time() + (block or 0) / 1000.0 if block else None
        )
        # Resolve "$" to the current tail id so that subsequent xadds are
        # surfaced (matches real Redis semantics).
        resolved: dict[str, str] = {}
        for stream, last_id in streams.items():
            if last_id == "$":
                msgs = self._streams.get(stream, [])
                resolved[stream] = msgs[-1][0] if msgs else "0-0"
            else:
                resolved[stream] = last_id
        while True:
            out: list = []
            for stream, last_id in resolved.items():
                msgs = self._streams.get(stream, [])
                new_msgs = [m for m in msgs if m[0] > last_id]
                if new_msgs:
                    out.append((stream, new_msgs[:count]))
            if out:
                return out
            if deadline is None:
                return []
            if asyncio.get_event_loop().time() >= deadline:
                return []
            await asyncio.sleep(0.01)

    async def xgroup_create(
        self, stream: str, group: str, id: str = "$", mkstream: bool = False
    ) -> bool:
        if (stream, group) in self._groups:
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self._groups[(stream, group)] = {"last_delivered_id": id}
        if mkstream:
            self._streams.setdefault(stream, [])
        return True

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 10,
        block: int | None = None,
    ) -> list:
        deadline = (
            asyncio.get_event_loop().time() + (block or 0) / 1000.0 if block else None
        )
        while True:
            out: list = []
            for stream in streams:
                state = self._groups.get((stream, group))
                if state is None:
                    continue
                last = state["last_delivered_id"]
                msgs = self._streams.get(stream, [])
                if last == "$":
                    delivered: list = []
                    state["last_delivered_id"] = msgs[-1][0] if msgs else "$"
                else:
                    delivered = [m for m in msgs if m[0] > last]
                    if delivered:
                        state["last_delivered_id"] = delivered[-1][0]
                if delivered:
                    out.append((stream, delivered[:count]))
            if out:
                return out
            if deadline is None:
                return []
            if asyncio.get_event_loop().time() >= deadline:
                return []
            await asyncio.sleep(0.01)

    async def xack(self, stream: str, group: str, msg_id: str) -> int:
        return 1


__all__ = ["FakeRedis"]
