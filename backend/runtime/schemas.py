"""Runtime schemas: explicit execution states, approvals, results."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ExecutionState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    EXECUTING = "EXECUTING"
    TOOL_CALL = "TOOL_CALL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.CREATED: {ExecutionState.PLANNING, ExecutionState.FAILED},
    ExecutionState.PLANNING: {ExecutionState.EXECUTING, ExecutionState.WAITING_FOR_PERMISSION,
                              ExecutionState.COMPLETED, ExecutionState.FAILED},
    ExecutionState.EXECUTING: {ExecutionState.TOOL_CALL, ExecutionState.VERIFYING,
                               ExecutionState.WAITING_FOR_PERMISSION, ExecutionState.COMPLETED,
                               ExecutionState.FAILED},
    ExecutionState.TOOL_CALL: {ExecutionState.EXECUTING, ExecutionState.WAITING_FOR_PERMISSION,
                               ExecutionState.VERIFYING, ExecutionState.FAILED},
    ExecutionState.WAITING_FOR_PERMISSION: {ExecutionState.EXECUTING, ExecutionState.FAILED},
    ExecutionState.VERIFYING: {ExecutionState.COMPLETED, ExecutionState.FAILED},
    ExecutionState.COMPLETED: set(),
    ExecutionState.FAILED: set(),
}


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    id: str
    execution_id: str
    agent: str
    tool: str
    action: str
    resource: str = ""
    reason: str = ""
    risk: str = "medium"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Execution(BaseModel):
    id: str
    state: ExecutionState = ExecutionState.CREATED
    agent: str = ""
    skill: str | None = None
    user_request: str = ""
    result: str | None = None
    error: str | None = None
    pending_approval_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[dict[str, Any]] = []
