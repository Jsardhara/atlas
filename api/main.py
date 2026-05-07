"""ATLAS FastAPI application."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Make ``agents/`` available so ``shared.protocols``, ``shared.config``, and
# ``shared.claude_client`` resolve when the API is launched as ``python -m
# atlas.api.main`` from the repo root.
_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / "agents"
if _AGENTS.is_dir() and str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from .config import get_settings  # noqa: E402
from .dependencies import init_db  # noqa: E402
from .pipeline_orchestrator import PipelineOrchestrator  # noqa: E402
from .routers import (  # noqa: E402
    agents,
    cost,
    pipeline,
    portfolio,
    signals,
    strategies,
    system,
    terminal,
    trades,
)
from .websocket.router import router as ws_router  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.database_url)
    app.state.redis_url = settings.redis_url
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Pipeline orchestrator: deterministic Python service replacing Commander.
    orch_engine = create_async_engine(
        settings.database_url, pool_size=2, max_overflow=4, echo=False
    )
    orch_session_factory = async_sessionmaker(orch_engine, expire_on_commit=False)
    orchestrator = PipelineOrchestrator(app.state.redis, orch_session_factory)
    app.state.orchestrator = orchestrator
    try:
        await orchestrator.start()
    except Exception as exc:  # noqa: BLE001 — startup must not crash the app
        logger.warning("PipelineOrchestrator failed to start: %s", exc)

    logger.info("ATLAS API started")
    try:
        yield
    finally:
        try:
            await orchestrator.stop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("PipelineOrchestrator stop error: %s", exc)
        await orch_engine.dispose()
        await app.state.redis.aclose()
        logger.info("ATLAS API shutting down")


app = FastAPI(
    title="ATLAS Trading API",
    description="Autonomous Trading & Learning Agent System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(agents.router)
app.include_router(trades.router)
app.include_router(portfolio.router)
app.include_router(signals.router)
app.include_router(strategies.router)
app.include_router(terminal.router)
app.include_router(system.router)
app.include_router(pipeline.router)
app.include_router(cost.router)
app.include_router(ws_router)
