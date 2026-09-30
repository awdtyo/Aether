"""Experimental skill discovery: propose reusable skills from repeated work.

Only *proposes*. A skill definition is written to disk exclusively through the
explicit approve endpoint — never silently, never by the model.
"""
from __future__ import annotations

import json
import re
from pydantic import BaseModel

MIN_REPEATS = 3


class SkillProposal(BaseModel):
    id: str  # stable slug for the approve endpoint
    name: str
    description: str
    evidence: list[str] = []  # example user requests
    count: int = 0
    agent: str = "personal"
    required_tools: list[str] = []
    required_permissions: list[str] = []
    status: str = "proposed"


_STOP = {"my", "the", "a", "an", "for", "to", "me", "please", "and", "with", "on"}


def _signature(text: str) -> str:
    toks = [t for t in re.findall(r"[a-z]+", text.lower()) if t not in _STOP]
    return " ".join(toks[:4])


def find_proposals(executions: list, existing_names: set[str],
                   agent_tools: dict[str, list[str]] | None = None) -> list[SkillProposal]:
    """Group COMPLETED executions by (agent, request signature)."""
    groups: dict[tuple[str, str], list] = {}
    for ex in executions:
        state = ex.state.value if hasattr(ex.state, "value") else str(ex.state)
        if state != "COMPLETED" or not (ex.user_request or "").strip():
            continue
        key = (ex.agent or "personal", _signature(ex.user_request))
        groups.setdefault(key, []).append(ex)
    proposals = []
    for (agent, sig), exs in sorted(groups.items()):
        if len(exs) < MIN_REPEATS or not sig:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", f"{agent}-{sig}").strip("-")[:48]
        if slug in existing_names or any(slug in n or n in slug for n in existing_names):
            continue
        name = slug
        proposals.append(SkillProposal(
            id=slug, name=name,
            description=f"Discovered from {len(exs)} similar completed requests (e.g. {exs[0].user_request[:80]!r}).",
            evidence=[e.user_request[:140] for e in exs[:5]],
            count=len(exs), agent=agent,
            required_tools=(agent_tools or {}).get(agent, []),
            required_permissions=["review on approve"]))
    return proposals


def render_skill_yaml(proposal: SkillProposal) -> str:
    return (f"name: {proposal.name}\n"
            f"description: {json.dumps(proposal.description)}\n"
            "version: 0.1.0\n"
            f"agent: {proposal.agent}\n"
            "instructions: >\n"
            f"  Discovered workflow (approved by user). Handle requests like: "
            f"{'; '.join(proposal.evidence[:3])}\n"
            "inputs: {request: string}\n"
            "outputs: {result: string}\n"
            f"required_tools: [{', '.join(proposal.required_tools)}]\n"
            f"required_permissions: [{', '.join(p for p in proposal.required_permissions if p != 'review on approve')}]\n")
