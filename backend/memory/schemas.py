"""Structured memory schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    PROJECT = "PROJECT"
    GOAL = "GOAL"
    DECISION = "DECISION"
    EXPERIENCE = "EXPERIENCE"
    SKILL = "SKILL"
    WORKFLOW = "WORKFLOW"


class MemoryCreate(BaseModel):
    type: MemoryType
    content: str = Field(min_length=1, max_length=8000)
    source: str = "conversation"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class MemoryUpdate(BaseModel):
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    last_verified: datetime | None = None


class Memory(BaseModel):
    id: str
    type: MemoryType
    content: str
    source: str
    confidence: float
    created_at: datetime
    updated_at: datetime
    last_verified: datetime | None = None
    score: float | None = None  # search relevance, not persisted

    model_config = {"from_attributes": True}


class MemorySearchQuery(BaseModel):
    query: str = ""
    types: list[MemoryType] | None = None
    limit: int = Field(default=8, ge=1, le=50)
