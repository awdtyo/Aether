"""Async DB engine + session factory.

Resolution order:
1. Explicit DATABASE_URL environment variable (e.g. Postgres in Docker).
2. A non-default database_url from config file (advanced override).
3. Default: SQLite inside the private AETHER_DATA_DIR (outside the repo).

SQLite files from older repo-relative layouts are migrated once (copied,
never moved or deleted) so existing memories survive the upgrade.
"""
from __future__ import annotations

import os
import shutil

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

_DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./aether.db"

_LEGACY_CANDIDATES = ("./aether.db", "backend/aether.db")


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def reset_db_state() -> None:
    """Test helper: drop cached engine/factory (uses tmp dirs in tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def resolve_database_url() -> str:
    settings = get_settings()
    explicit = os.environ.get("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    if settings.database_url != _DEFAULT_SQLITE_URL:
        return settings.database_url
    return settings.memory_db_url()


def build_session_factory(url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        url, echo=False,
        **({"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}))
    return async_sessionmaker(engine, expire_on_commit=False)


def migrate_legacy_db(target: str) -> str | None:
    """One-time copy of a repo-local legacy SQLite DB into the data dir.

    Returns the source path copied, or None. Never deletes the original."""
    if not target.startswith("sqlite"):
        return None
    import logging
    from pathlib import Path
    from urllib.parse import unquote
    from urllib.request import url2pathname

    dest = Path(unquote(url2pathname(target.split("///", 1)[-1])))
    if dest.exists():
        return None
    for candidate in _LEGACY_CANDIDATES:
        src = Path(candidate)
        if src.is_file():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                logging.getLogger("aether").info(
                    "migrated legacy memory db %s -> %s (original kept)", src, dest)
                return str(src)
            except OSError as e:
                logging.getLogger("aether").warning("legacy db migration failed: %s", e)
                return None
    return None


def get_engine():
    global _engine
    if _engine is None:
        url = resolve_database_url()
        migrate_legacy_db(url)
        settings = get_settings()
        kwargs = {}
        if url.startswith("sqlite"):
            settings.data_dir()  # ensure private dirs exist before connect
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(url, echo=False, **kwargs)
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
