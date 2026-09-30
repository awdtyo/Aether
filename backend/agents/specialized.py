"""Specialized agents. Each uses injected deps (memory/tools/router/audit)."""
from __future__ import annotations

from agents.base import Agent, AgentContext, AgentResult


class PersonalAgent(Agent):
    name = "personal"
    description = "General personal requests, intent routing, memory-aware answers"
    capabilities = ["intent understanding", "memory recall", "direct answers", "delegation"]
    tools = ["notes", "calendar", "web"]

    async def run(self, ctx: AgentContext, deps) -> AgentResult:
        mem_txt = "\n".join(f"- [{m.get('type')}] {m.get('content')}" for m in ctx.memories[:6])
        resp = await deps.router.generate(ctx.user_request, context=mem_txt,
                                          system="You are AETHER PersonalAgent. Be concise and helpful.")
        return AgentResult(text=resp.text)


class ResearchAgent(Agent):
    name = "research"
    description = "Research briefs, paper analysis, experiment recall"
    capabilities = ["memory search", "summarization", "research briefs"]
    tools = ["notes", "web", "email", "calendar"]

    async def run(self, ctx: AgentContext, deps) -> AgentResult:
        mem_txt = "\n".join(f"- [{m.get('type')}] {m.get('content')}" for m in ctx.memories[:8])
        cal, _ = await deps.tools.run("research", "calendar", "read", {}, "", "brief context",
                                      audit=deps.audit, execution_id=ctx.execution_id)
        cal_txt = str((cal.output or {}).get("events", []))[:1200]
        resp = await deps.router.generate(
            f"Prepare a concise research/meeting brief for: {ctx.user_request}\nCalendar: {cal_txt}",
            tier="reasoning", context=mem_txt,
            system="You are AETHER ResearchAgent. Produce: Objective, Background, Key points, Open questions, Next actions.")
        return AgentResult(text=resp.text)


class DeveloperAgent(Agent):
    name = "developer"
    description = "Repo inspection, TODO surfacing, project status, dev plans"
    capabilities = ["repo inspection", "TODO scan", "status summary", "dev plans"]
    tools = ["filesystem", "git", "github"]

    async def run(self, ctx: AgentContext, deps) -> AgentResult:
        from core.config import get_settings
        repo = get_settings().git_allowlist.split(",")[0].strip() or get_settings().workspace_root
        out: list[str] = []
        for action in ("status", "log"):
            res, _ = await deps.tools.run("developer", "git", action, {"repo": repo},
                                          repo, "project status", audit=deps.audit,
                                          execution_id=ctx.execution_id)
            if res.ok:
                out.append(f"## git {action}\n{(res.output or {}).get('output', '')[:1500]}")
            else:
                out.append(f"## git {action}\n(unavailable: {res.error})")
        mem_txt = "\n".join(f"- [{m.get('type')}] {m.get('content')}" for m in ctx.memories[:6])
        resp = await deps.router.generate(
            f"Summarize project status and next dev steps for: {ctx.user_request}\n" + "\n".join(out),
            context=mem_txt, system="You are AETHER DeveloperAgent. Be concrete: status, TODOs, suggested plan.")
        return AgentResult(text=resp.text + "\n\n" + "\n".join(out))


class PlanningAgent(Agent):
    name = "planning"
    description = "Daily plans, priorities, goals"
    capabilities = ["goal review", "daily plans", "priorities"]
    tools = ["calendar", "notes"]

    async def run(self, ctx: AgentContext, deps) -> AgentResult:
        mem_txt = "\n".join(f"- [{m.get('type')}] {m.get('content')}" for m in ctx.memories[:8])
        cal, _ = await deps.tools.run("planning", "calendar", "read", {}, "", "daily plan",
                                      audit=deps.audit, execution_id=ctx.execution_id)
        cal_txt = str((cal.output or {}).get("events", []))[:1200]
        resp = await deps.router.generate(
            f"Create a focused daily plan for: {ctx.user_request}\nCalendar: {cal_txt}",
            context=mem_txt,
            system="You are AETHER PlanningAgent. Output: Top 3 priorities, time blocks, risks.")
        return AgentResult(text=resp.text)


AGENTS: dict[str, Agent] = {a.name: a for a in
                            [PersonalAgent(), ResearchAgent(), DeveloperAgent(), PlanningAgent()]}


def pick_agent(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("research", "paper", "meeting", "brief", "experiment", "study")):
        return "research"
    if any(k in t for k in ("code", "repo", "git", "bug", "deploy", "todo", "project status", "commit")):
        return "developer"
    if any(k in t for k in ("plan", "schedule", "today", "tomorrow", "priority", "priorities", "goal")):
        return "planning"
    return "personal"
