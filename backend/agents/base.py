"""Agent base class + registry. Agents get services, never the DB."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class AgentContext(BaseModel):
    execution_id: str
    user_request: str
    memories: list[dict[str, Any]] = []
    args: dict[str, Any] = {}


class AgentResult(BaseModel):
    text: str
    tool_calls: list[dict[str, Any]] = []
    memories_to_save: list[dict[str, Any]] = []


class Agent:
    name = "base"
    description = ""
    capabilities: list[str] = []
    tools: list[str] = []

    async def run(self, ctx: AgentContext, deps) -> AgentResult:
        raise NotImplementedError
