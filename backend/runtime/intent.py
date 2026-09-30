"""LLM-driven intent classification with deterministic rules fallback.

The model may *propose* (agent, skill, plan) but the runtime validates every
name against the live registries. Security decisions never come from here —
the policy engine stays authoritative downstream.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    agent: Literal["personal", "research", "developer", "planning"] = "personal"
    skill: str | None = None
    plan: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_PLANNER_SYSTEM = (
    "You are AETHER's intent planner. Given a user request, choose the best "
    "agent and at most one skill, plus a short task plan. "
    "Agents: personal (general), research (research/meetings/briefs), "
    "developer (code/repos/git/status), planning (plans/schedules/goals). "
    "Only pick a skill from the provided list when the request clearly matches "
    "its description; otherwise null. Respond with JSON only.")


async def classify_intent(text: str, router, skills) -> tuple[IntentDecision, str]:
    """Returns (decision, source) where source is 'llm' or 'rules'.

    Falls back to keyword rules whenever the provider cannot do structured
    output (mock/offline) or the model's choice fails registry validation."""
    from agents.specialized import pick_agent

    catalog = [{"name": s.name, "description": s.description, "agent": s.agent}
               for s in skills.list()]
    try:
        prompt = (f"Skills: {catalog}\nRequest: {text[:500]}\n"
                  "JSON keys: agent, skill (name or null), plan (<=6 steps), confidence.")
        decision = await router.generate_structured(prompt, IntentDecision, _PLANNER_SYSTEM)
        valid_agents = {"personal", "research", "developer", "planning"}
        valid_skills = {s["name"] for s in catalog}
        if decision.agent not in valid_agents:
            raise ValueError(f"unknown agent {decision.agent}")
        if decision.skill is not None and decision.skill not in valid_skills:
            decision.skill = None  # unknown skill -> treat as no skill, keep agent
        return decision, "llm"
    except Exception:
        skill = skills.match(text)
        agent = (skill.agent if skill else None) or _rule_agent(text, pick_agent)
        return IntentDecision(agent=agent,  # type: ignore[arg-type]
                              skill=skill.name if skill else None,
                              plan=[], confidence=0.5), "rules"


def _rule_agent(text: str, pick_agent) -> str:
    t = text.lower()
    if any(k in t for k in ("send", "email", "share", "brief")) and \
       any(k in t for k in ("research", "meeting", "group", "brief")):
        return "research"
    return pick_agent(text)
