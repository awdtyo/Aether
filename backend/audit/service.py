"""Audit schemas + service (DB-backed when available, else in-memory)."""
from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel


class AuditEvent(BaseModel):
    id: int | None = None
    timestamp: datetime = datetime.now(timezone.utc)
    execution_id: str = ""
    agent: str = ""
    action: str = ""
    resource: str = ""
    permission: str = ""
    reason: str = ""
    status: str = ""
    duration_ms: float | None = None


def _redact(text: str) -> str:
    low = text.lower()
    for secret in ("api_key", "apikey", "token", "password", "secret"):
        if secret in low:
            return "[redacted]"
    return text[:2000]


class AuditService:
    def __init__(self, session_factory=None):
        self._factory = session_factory
        self._events: list[AuditEvent] = []
        self._seq = 0

    async def record(self, execution_id: str = "", agent: str = "", action: str = "",
                     resource: str = "", permission: str = "", reason: str = "",
                     status: str = "", duration_ms: float | None = None) -> AuditEvent:
        from database.models import AuditRow

        ev = AuditEvent(timestamp=datetime.now(timezone.utc), execution_id=execution_id,
                        agent=agent, action=_redact(action), resource=_redact(resource),
                        permission=permission, reason=_redact(reason), status=status,
                        duration_ms=duration_ms)
        if self._factory is None:
            self._seq += 1
            ev.id = self._seq
            self._events.append(ev)
            return ev
        async with self._factory() as s:
            row = AuditRow(execution_id=ev.execution_id, agent=ev.agent, action=ev.action,
                           resource=ev.resource, permission=ev.permission, reason=ev.reason,
                           status=ev.status, duration_ms=ev.duration_ms, timestamp=ev.timestamp)
            s.add(row)
            await s.commit()
            await s.refresh(row)
            ev.id = row.id
            return ev

    async def list(self, execution_id: str | None = None, limit: int = 200) -> list[AuditEvent]:
        from database.models import AuditRow
        from sqlalchemy import select

        if self._factory is None:
            evs = [e for e in self._events if not execution_id or e.execution_id == execution_id]
            return evs[-limit:][::-1]
        async with self._factory() as s:
            q = select(AuditRow).order_by(AuditRow.id.desc()).limit(limit)
            if execution_id:
                q = q.where(AuditRow.execution_id == execution_id)
            rows = (await s.execute(q)).scalars().all()
            return [AuditEvent(id=r.id, timestamp=r.timestamp, execution_id=r.execution_id,
                               agent=r.agent, action=r.action, resource=r.resource,
                               permission=r.permission, reason=r.reason, status=r.status,
                               duration_ms=r.duration_ms) for r in rows]
