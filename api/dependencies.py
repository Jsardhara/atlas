"""FastAPI dependency injection helpers."""
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory = None


def init_db(database_url: str):
    global _engine, _session_factory
    _engine = create_async_engine(database_url, pool_size=10, max_overflow=20, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_db(request: Request):
    if _session_factory is None:
        raise RuntimeError("DB not initialised")
    async with _session_factory() as session:
        yield session
