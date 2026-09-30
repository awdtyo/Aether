"""SQLAlchemy models. pgvector VECTOR on postgres, JSON fallback on sqlite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRow(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    execution_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    agent: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), index=True, default="")
    resource: Mapped[str] = mapped_column(String(256), default="")
    permission: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
