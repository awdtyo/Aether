"""REST API: command, memory, agents, skills, tools, approvals, activity, models."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agents.specialized import AGENTS
from api import deps as d
from memory.schemas import MemoryCreate, MemorySearchQuery, MemoryType, MemoryUpdate
from runtime.schemas import ApprovalStatus

router = APIRouter()


# -- command ---------------------------------------------------------------
class CommandIn(BaseModel):
    message: str
    session_id: str | None = None


@router.post("/command")
async def command(body: CommandIn):
    ex = await d.orchestrator.handle(body.message)
    return {"execution_id": ex.id, "state": ex.state.value, "agent": ex.agent,
            "skill": ex.skill, "result": ex.result, "error": ex.error,
            "pending_approval_id": ex.pending_approval_id}


@router.get("/executions")
async def executions(limit: int = 20):
    return [e.model_dump() for e in d.store.list(limit)]


@router.get("/executions/{execution_id}")
async def execution_detail(execution_id: str):
    ex = d.store.get(execution_id)
    if not ex:
        return {"error": "not found"}
    events = await d.audit.list(execution_id=execution_id, limit=200)
    from runtime.timeline import build_timeline
    return {"execution": ex.model_dump(),
            "events": [e.model_dump() for e in events],
            "timeline": build_timeline(ex, events)}


# -- approvals ---------------------------------------------------------------
@router.get("/approvals/pending")
async def approvals_pending():
    return [a.model_dump() for a in d.store.pending()]


class ApprovalResolve(BaseModel):
    approved: bool


@router.post("/approvals/{approval_id}/resolve")
async def approval_resolve(approval_id: str, body: ApprovalResolve):
    ap = d.store.approvals.get(approval_id)
    if not ap:
        return {"error": "not found"}
    d.store.resolve_approval(approval_id, body.approved)
    ex = await d.orchestrator.resume_after_approval(ap.execution_id, body.approved)
    return {"approval": d.store.approvals[approval_id].model_dump(),
            "execution": ex.model_dump() if ex else None}


# -- memory ------------------------------------------------------------------
@router.post("/memory")
async def memory_create(body: MemoryCreate):
    return (await d.memory.create(body)).model_dump()


@router.get("/memory")
async def memory_list(type: str | None = None, source: str | None = None, limit: int = 100):
    types = [MemoryType(type)] if type else None
    mems = await d.memory.list(types, limit * 2 if source else limit)
    if source:
        mems = [m for m in mems if m.source == source][:limit]
    return [m.model_dump() for m in mems]


@router.post("/memory/search")
async def memory_search(body: MemorySearchQuery):
    return [m.model_dump() for m in await d.memory.search(body.query, body.types, body.limit)]


@router.get("/memory/{mem_id}")
async def memory_get(mem_id: str):
    m = await d.memory.get(mem_id)
    return m.model_dump() if m else {"error": "not found"}


@router.get("/memory/{mem_id}/related")
async def memory_related(mem_id: str, limit: int = 5):
    m = await d.memory.get(mem_id)
    if not m:
        return {"error": "not found"}
    hits = [h for h in await d.memory.search(m.content, limit=limit + 1) if h.id != mem_id]
    return [h.model_dump() for h in hits[:limit]]


@router.patch("/memory/{mem_id}")
async def memory_update(mem_id: str, body: MemoryUpdate):
    m = await d.memory.update(mem_id, body)
    return m.model_dump() if m else {"error": "not found"}


@router.delete("/memory/{mem_id}")
async def memory_delete(mem_id: str):
    return {"deleted": await d.memory.delete(mem_id)}


# -- agents / skills / tools ---------------------------------------------------
@router.get("/agents")
async def agents():
    out = []
    for name, a in AGENTS.items():
        active = [e.model_dump() for e in d.store.list(50)
                  if e.agent == name and e.state.value not in ("COMPLETED", "FAILED")]
        out.append({"name": name, "description": a.description,
                    "capabilities": a.capabilities, "tools": a.tools,
                    "active": active})
    return out


@router.get("/skills")
async def skills():
    d.skills.reload()
    return [s.model_dump() for s in d.skills.list()]


class SkillRun(BaseModel):
    input: str = ""
    args: dict = {}


@router.post("/skills/{name}/run")
async def skill_run(name: str, body: SkillRun):
    skill = next((s for s in d.skills.list() if s.name == name), None)
    if not skill:
        return {"error": "unknown skill"}
    prompt = f"[{skill.name}] {skill.instructions}\nRequest: {body.input or name}"
    ex = await d.orchestrator.handle(prompt)
    return {"execution_id": ex.id, "state": ex.state.value, "result": ex.result}


@router.get("/tools")
async def tools():
    return [s.model_dump() for s in d.tools.list()]


class ToolCallIn(BaseModel):
    action: str
    args: dict = {}
    resource: str = ""
    reason: str = "manual UI call"


@router.post("/tools/{name}/call")
async def tool_call(name: str, body: ToolCallIn):
    res, verdict = await d.tools.run("user", name, body.action, body.args,
                                     body.resource, body.reason,
                                     audit=d.audit, execution_id="manual")
    return {"result": res.model_dump(), "policy": verdict.model_dump()}


# -- skill discovery (experimental: propose only; creation needs approval) ---
@router.get("/discovery/proposals")
async def discovery_proposals():
    from agents.specialized import AGENTS
    from skills.discovery import find_proposals
    return [p.model_dump() for p in find_proposals(
        d.store.list(200), {s.name for s in d.skills.list()},
        {name: a.tools for name, a in AGENTS.items()})]


@router.post("/discovery/{proposal_id}/approve")
async def discovery_approve(proposal_id: str):
    import re
    from pathlib import Path
    from agents.specialized import AGENTS
    from skills.discovery import find_proposals, render_skill_yaml
    proposals = {p.id: p for p in find_proposals(
        d.store.list(200), {s.name for s in d.skills.list()},
        {name: a.tools for name, a in AGENTS.items()})}
    p = proposals.get(proposal_id)
    if not p:
        return {"error": "proposal not found (it may no longer qualify)"}
    slug = re.sub(r"[^a-z0-9-]+", "-", p.name.lower()).strip("-")[:48]
    base = next((b for b in (Path("skills"), Path("../skills")) if b.exists()), Path("skills"))
    target = base / f"discovered-{slug}" / "skill.yaml"  # one level: registry scans */skill.yaml
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_skill_yaml(p))
    d.skills.reload()
    await d.audit.record(execution_id="", agent="user", action="skill_created",
                         resource=p.name, reason="discovery proposal approved",
                         status="ok")
    return {"created": p.name, "path": str(target)}


# -- activity / models -----------------------------------------------------------
@router.get("/activity")
async def activity(limit: int = 100):
    return [e.model_dump() for e in await d.audit.list(limit=limit)]


@router.get("/models")
async def models():
    from core.config import get_settings
    return {"provider": d.router.provider.name, "models": d.router.models,
            "status": d.router.status(),  # safe: no keys or headers
            "demo_mode": get_settings().demo_mode,
            "db": "postgres" if d.db_available else "sqlite/in-memory"}
