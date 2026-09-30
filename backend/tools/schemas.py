"""Tool schemas: every tool declares permissions + risk up front."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolSpec(BaseModel):
    name: str
    description: str
    required_permissions: list[str] = []
    risk_level: RiskLevel = RiskLevel.LOW


class ToolCall(BaseModel):
    tool: str
    action: str
    args: dict[str, Any] = {}
    resource: str = ""


class ToolResult(BaseModel):
    ok: bool
    output: Any = None
    error: str | None = None
