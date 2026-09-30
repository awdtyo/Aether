"""Orchestrator: intent → agent → skill → policy-gated tools → verify → memory.

Simple requests stay simple (direct agent answer). Sensitive tool actions
(APPROVAL_REQUIRED) pause execution and create an approval request instead of
executing. DENY stops the step with an explanation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from agents.base import AgentContext
from agents.specialized import AGENTS, pick_agent
from memory.service import worth_persisting
from memory.schemas import MemoryCreate, MemoryType
from policies.schemas import PolicyCheck
from runtime.schemas import Execution, ExecutionState


@dataclass
class Deps:
    memory: object
    tools: object
    audit: object
    router: object
    policy: object


EMAIL_SEND = ("email", "send")


class Orchestrator:
    def __init__(self, store, skills, deps: Deps):
        self.store = store
        self.skills = skills
        self.deps = deps

    # -- public API -------------------------------------------------------
    async def handle(self, text: str) -> Execution:
        ex = self.store.create(text)
        t0 = time.monotonic()
        try:
            self.store.transition(ex, ExecutionState.PLANNING, "intent analysis")
            skill = self.skills.match(text)
            agent_name = (skill.agent if skill else None) or self._route_agent(text)
            ex.agent, ex.skill = agent_name, (skill.name if skill else None)
            await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                         action="agent_started",
                                         resource=skill.name if skill else "direct",
                                         reason=text[:300], status="started")

            self.store.transition(ex, ExecutionState.EXECUTING, f"agent={agent_name}")
            await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                         action="memory_read", reason=text[:200],
                                         status="started")
            mems = await self.deps.memory.search(text, limit=8)
            await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                         action="memory_read",
                                         reason=f"{len(mems)} memories retrieved", status="ok")
            ctx = AgentContext(execution_id=ex.id, user_request=text,
                               memories=[m.model_dump() for m in mems])

            # Skill pre-step: detect sensitive side effects up front (demo flow:
            # "send the brief..." → email.send needs approval before executing).
            sensitive = self._detect_sensitive(text)
            if sensitive:
                tool, action = sensitive
                verdict = self.deps.policy.check(PolicyCheck(
                    agent=agent_name, tool=tool, action=action,
                    resource=text[:200], reason=f"Requested: {text[:200]}"))
                await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                             action=f"{tool}.{action}", permission=verdict.decision.value,
                                             reason=verdict.reason, status="checked")
                if verdict.decision.value == "DENY":
                    return await self._finish(ex, agent_name, t0,
                                              f"Blocked by policy: {verdict.reason}", failed=True)
                if verdict.decision.value == "APPROVAL_REQUIRED":
                    ap = self.store.add_approval(ex.id, agent_name, tool, action,
                                                 resource="research group" if "brief" in text.lower() else "",
                                                 reason=f"Send the generated brief: '{text[:160]}'",
                                                 risk="high" if tool == "email" else "medium")
                    self.store.transition(ex, ExecutionState.WAITING_FOR_PERMISSION,
                                          f"approval={ap.id}")
                    await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                                 action="approval_requested",
                                                 resource=f"{tool}.{action}", reason=ap.reason,
                                                 status="pending")
                    ex.pending_approval_id = ap.id
                    ex.result = (f"Paused for approval: {agent_name} wants to {action} via {tool}.\n"
                                 f"Reason: {ap.reason}\nApprove in the Command Center to continue.")
                    return ex

            agent = AGENTS[agent_name]
            self.store.transition(ex, ExecutionState.TOOL_CALL, f"agent={agent_name}")
            result = await agent.run(ctx, self.deps)
            self.store.transition(ex, ExecutionState.VERIFYING, "verifying result")

            # Persist durable facts (gated, never the whole chat).
            if worth_persisting(text):
                try:
                    await self.deps.memory.create(MemoryCreate(
                        type=self._classify_memory(text), content=text[:2000],
                        source="conversation", confidence=0.75))
                    await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                                 action="memory_created", reason="durable fact",
                                                 status="ok")
                except Exception:
                    pass

            prefix = f"[{skill.name} v{skill.version}]\n" if skill else ""
            return await self._finish(ex, agent_name, t0, prefix + result.text)
        except Exception as e:
            ex.error = f"{type(e).__name__}: {e}"
            try:
                self.store.force(ex, ExecutionState.FAILED, str(ex.error))
            except Exception:
                pass
            await self.deps.audit.record(execution_id=ex.id, agent=ex.agent or "?",
                                         action="error", reason=ex.error[:500], status="failed")
            return ex

    async def resume_after_approval(self, execution_id: str, approved: bool) -> Execution | None:
        ex = self.store.get(execution_id)
        if not ex or ex.state != ExecutionState.WAITING_FOR_PERMISSION:
            return None
        agent_name = ex.agent or "personal"
        if not approved:
            await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                         action="approval_denied", status="denied",
                                         reason="user denied")
            return await self._finish(ex, agent_name, time.monotonic(),
                                      "Action denied by user. Execution stopped.", failed=True)
        await self.deps.audit.record(execution_id=ex.id, agent=agent_name,
                                     action="approval_granted", status="approved",
                                     reason="user approved")
        self.store.transition(ex, ExecutionState.EXECUTING, "resumed after approval")
        # Execute the approved side effect (MVP: email.send draft→send via outbox).
        res, _ = await self.deps.tools.run(agent_name, "email", "send",
                                           {"to": ["research group"],
                                            "subject": "Meeting brief from AETHER",
                                            "body": ex.user_request[:2000]},
                                           "research group", "user-approved send",
                                           audit=self.deps.audit, execution_id=ex.id)
        tail = f"\n\nEmail send: {'done (MVP outbox)' if res.ok else 'failed: ' + str(res.error)}"
        return await self._finish(ex, agent_name, time.monotonic(),
                                  (ex.result or "") + tail)

    # -- helpers -----------------------------------------------------------
    def _route_agent(self, text: str) -> str:
        t = text.lower()
        if any(k in t for k in ("send", "email", "share", "brief")) and \
           any(k in t for k in ("research", "meeting", "group", "brief")):
            return "research"
        return pick_agent(text)

    def _detect_sensitive(self, text: str) -> tuple[str, str] | None:
        t = text.lower()
        if any(k in t for k in ("send ", "send the", "email ", "mail ", "share ")) and \
           any(k in t for k in ("brief", "group", "team", "report", "summary")):
            return EMAIL_SEND
        if "commit" in t and ("git" in t or "code" in t or "repo" in t):
            return ("git", "commit")
        if "delete" in t and "calendar" in t:
            return ("calendar", "delete")
        return None

    def _classify_memory(self, text: str) -> MemoryType:
        t = text.lower()
        if "prefer" in t or "like " in t or "love " in t:
            return MemoryType.PREFERENCE
        if "decid" in t or "chose" in t:
            return MemoryType.DECISION
        if "goal" in t or "want to" in t:
            return MemoryType.GOAL
        if "project" in t:
            return MemoryType.PROJECT
        return MemoryType.FACT

    async def _finish(self, ex: Execution, agent: str, t0: float, result: str,
                      failed: bool = False) -> Execution:
        ms = (time.monotonic() - t0) * 1000
        self.store.force(ex, ExecutionState.FAILED if failed else ExecutionState.COMPLETED,
                         "done" if not failed else "failed")
        ex.result, duration = result, ms
        await self.deps.audit.record(execution_id=ex.id, agent=agent,
                                     action="agent_finished", reason=(result or "")[:300],
                                     status="failed" if failed else "ok", duration_ms=ms)
        return ex
