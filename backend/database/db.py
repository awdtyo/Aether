"""Async DB engine + session factory. SQLite by default, Postgres+pgvector in prod."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs = {}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(settings.database_url, echo=False, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    from database.models import Base as ModelsBase  # noqa: F401  (register models)

    engine = get_engine()
    async with engine.begin() as conn:
        try:
            from pgvector.sqlalchemy import Vector  # noqa: F401
        except Exception:
            pass
        await conn.run_sync(ModelsBase.metadata.create_all)
        # pgvector extension on postgres (best effort)
        try:
            if engine.url.get_backend_name() == "postgresql":
                await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            pass


async def get_session() -> AsyncSession:  # FastAPI dependency
    factory = get_session_factory()
    async with factory() as session:
        yield session
