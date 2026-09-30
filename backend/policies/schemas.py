"""Policy schemas — the engine is authoritative, never the LLM."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class PolicyCheck(BaseModel):
    agent: str
    tool: str
    action: str
    resource: str = ""
    reason: str = ""


class PolicyResult(BaseModel):
    decision: Decision
    reason: str
