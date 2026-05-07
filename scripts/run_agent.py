"""Host-side launcher for a single Atlas agent.

Usage::

    python scripts/run_agent.py oracle
    python scripts/run_agent.py architect
    python scripts/run_agent.py guardian
    python scripts/run_agent.py trader
    python scripts/run_agent.py sage

Loads ``.env`` via ``python-dotenv``, validates required environment, sets up
JSON logging, imports ``agents.<name>.main`` and runs it under ``asyncio.run``.
SIGINT and SIGTERM trigger a clean shutdown.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

ATLAS_ROOT = Path(__file__).resolve().parent.parent

VALID_AGENTS = ("oracle", "architect", "guardian", "trader", "sage")

REQUIRED_ENV_VARS = (
    "DATABASE_URL",
    "REDIS_URL",
    "ATLAS_BEARER_TOKEN",
)


class JsonLogFormatter(logging.Formatter):
    """Minimal JSON log line formatter — suitable for `docker logs` style tail."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging(agent_name: str) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(os.environ.get("ATLAS_LOG_LEVEL", "INFO"))
    return logging.getLogger(f"atlas.{agent_name}")


def _load_dotenv() -> None:
    """Load ``.env`` via ``python-dotenv`` if available; else inline parse."""
    env_path = ATLAS_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv(env_path)
        return
    except ImportError:
        pass

    # Fallback: minimal parser, for the case where python-dotenv is not yet
    # installed in the host venv.
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _validate_env(log: logging.Logger) -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        log.error("missing required env vars: %s", ", ".join(missing))
        raise SystemExit(2)


def _resolve_main(agent_name: str) -> Callable[[], Awaitable[Any]]:
    """Import ``agents.<name>`` and return its ``main`` coroutine factory.

    Tries common entrypoint names in order: ``main``, ``run``, ``Agent.run``.
    """
    if str(ATLAS_ROOT) not in sys.path:
        sys.path.insert(0, str(ATLAS_ROOT))
    if str(ATLAS_ROOT / "agents") not in sys.path:
        sys.path.insert(0, str(ATLAS_ROOT / "agents"))

    candidates = (
        f"agents.{agent_name}.main",
        f"agents.{agent_name}.agent",
        f"{agent_name}.main",
        f"{agent_name}.agent",
    )
    last_exc: Exception | None = None
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            last_exc = exc
            continue

        for attr in ("main", "run", "start"):
            entrypoint = getattr(module, attr, None)
            if callable(entrypoint):
                return entrypoint  # type: ignore[return-value]

        agent_cls = getattr(module, "Agent", None)
        if agent_cls is not None:
            instance = agent_cls()
            if hasattr(instance, "run"):
                return instance.run  # type: ignore[return-value]

    raise SystemExit(
        f"could not locate entrypoint for agent '{agent_name}'. "
        f"Tried: {', '.join(candidates)}. Last import error: {last_exc!r}"
    )


async def _run(entrypoint: Callable[[], Awaitable[Any]], log: logging.Logger) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(signame: str) -> None:
        log.info("received %s — shutting down", signame)
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _signal_handler, sig_name)
        except NotImplementedError:
            # Windows: add_signal_handler not supported. Fall back to default
            # handler (KeyboardInterrupt) — captured below.
            signal.signal(sig, lambda *_a, name=sig_name: _signal_handler(name))

    result = entrypoint()
    if not asyncio.iscoroutine(result):
        log.error("entrypoint did not return a coroutine: %r", result)
        return

    agent_task = asyncio.create_task(result)
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {agent_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if stop_task in done and not agent_task.done():
        agent_task.cancel()
        try:
            await agent_task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            log.info("agent cancelled (%s)", type(exc).__name__)
    else:
        for task in pending:
            task.cancel()
        if agent_task.exception() is not None:
            raise agent_task.exception()  # type: ignore[misc]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an Atlas agent on the host.")
    parser.add_argument("agent", choices=VALID_AGENTS)
    args = parser.parse_args(argv)

    _load_dotenv()
    log = _setup_logging(args.agent)
    log.info("starting agent=%s", args.agent)
    _validate_env(log)

    entrypoint = _resolve_main(args.agent)

    try:
        asyncio.run(_run(entrypoint, log))
    except KeyboardInterrupt:
        log.info("keyboard interrupt — exiting")
    except Exception:
        log.exception("agent crashed")
        return 1
    log.info("agent=%s stopped cleanly", args.agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
