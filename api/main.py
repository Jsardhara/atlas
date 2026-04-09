"""ATLAS FastAPI application."""
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .dependencies import init_db
from .routers import agents, portfolio, signals, strategies, system, terminal, trades
from .websocket.router import router as ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.database_url)
    app.state.redis_url = settings.redis_url
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    logger.info("ATLAS API started")
    yield
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
    allow_credentials=True,
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
app.include_router(ws_router)
