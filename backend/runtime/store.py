"""In-memory execution + approval store with validated state transitions."""
from __future__ import annotations

import uuid

from runtime.schemas import ApprovalRequest, ApprovalStatus, Execution, ExecutionState, TRANSITIONS


class ExecutionStore:
    def __init__(self):
        self.executions: dict[str, Execution] = {}
        self.approvals: dict[str, ApprovalRequest] = {}

    def create(self, user_request: str) -> Execution:
        ex = Execution(id=str(uuid.uuid4()), user_request=user_request)
        self.executions[ex.id] = ex
        return ex

    def get(self, execution_id: str) -> Execution | None:
        return self.executions.get(execution_id)

    def transition(self, ex: Execution, to: ExecutionState, note: str = "") -> Execution:
        allowed = TRANSITIONS.get(ex.state, set())
        if to not in allowed:
            raise ValueError(f"Illegal transition {ex.state} -> {to}")
        ex.state = to
        ex.history.append({"state": to.value, "note": note})
        from datetime import datetime, timezone
        ex.updated_at = datetime.now(timezone.utc)
        return ex

    def force(self, ex: Execution, to: ExecutionState, note: str = "") -> Execution:
        ex.state = to
        ex.history.append({"state": to.value, "note": note})
        return ex

    def list(self, limit: int = 50) -> list[Execution]:
        return sorted(self.executions.values(), key=lambda e: e.created_at,
                      reverse=True)[:limit]

    # -- approvals ---------------------------------------------------------
    def add_approval(self, execution_id: str, agent: str, tool: str, action: str,
                     resource: str, reason: str, risk: str = "medium") -> ApprovalRequest:
        ap = ApprovalRequest(id=str(uuid.uuid4())[:8], execution_id=execution_id,
                             agent=agent, tool=tool, action=action, resource=resource,
                             reason=reason, risk=risk)
        self.approvals[ap.id] = ap
        return ap

    def resolve_approval(self, approval_id: str, approved: bool) -> ApprovalRequest | None:
        ap = self.approvals.get(approval_id)
        if not ap or ap.status != ApprovalStatus.PENDING:
            return None
        ap.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        return ap

    def pending(self) -> list[ApprovalRequest]:
        return [a for a in self.approvals.values() if a.status == ApprovalStatus.PENDING]
