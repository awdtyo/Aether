"""Hackathon-polish tests: intent fallback, policy invariant, discovery, timeline, demo."""
import pytest

from runtime.schemas import Execution, ExecutionState


@pytest.mark.asyncio
async def test_intent_falls_back_to_rules_with_mock():
    from runtime.intent import classify_intent
    from models.router import ModelRouter
    from skills.registry import SkillRegistry
    decision, source = await classify_intent("Prepare my research meeting for tomorrow.",
                                             ModelRouter(), SkillRegistry(skills_dir="skills"))
    assert source == "rules"  # mock provider has no structured output
    assert decision.agent == "research" and decision.skill == "meeting-preparation"


@pytest.mark.asyncio
async def test_llm_intent_validated_against_registries():
    import json as _json
    from runtime.intent import classify_intent
    from skills.registry import SkillRegistry

    class FakeRouter:
        async def generate_structured(self, prompt, schema, system, tier="fast"):
            return schema.model_validate(
                {"agent": "research", "skill": "no-such-skill", "plan": [], "confidence": 0.9})

    decision, source = await classify_intent("summarize these papers",
                                             FakeRouter(), SkillRegistry(skills_dir="skills"))
    assert source == "llm" and decision.agent == "research"
    assert decision.skill is None  # unknown skill rejected, agent kept


@pytest.mark.asyncio
async def test_protected_tool_never_runs_without_policy_approval():
    """Invariant: no ALLOW decision -> no execution. Registry enforces this."""
    from policies.engine import PolicyEngine
    from tools import stubs
    from tools.registry import ToolRegistry
    before = len(stubs._sent)
    reg = ToolRegistry(policy=PolicyEngine())
    res, verdict = await reg.run("research", "email", "send",
                                 {"to": ["x"], "subject": "s", "body": "b"},
                                 "research group", audit=None, execution_id="t")
    assert verdict.decision.value == "APPROVAL_REQUIRED"
    assert not res.ok and len(stubs._sent) == before  # nothing executed
    res2, v2 = await reg.run("developer", "git", "merge", {}, "repo",
                             audit=None, execution_id="t")
    assert v2.decision.value == "DENY" and not res2.ok


def test_discovery_proposes_repeats_and_ignores_existing():
    from skills.discovery import find_proposals
    exs = [Execution(id=str(i), user_request="summarize this research paper please",
                     agent="research", state=ExecutionState.COMPLETED) for i in range(3)]
    exs.append(Execution(id="x", user_request="what is the time", agent="personal",
                         state=ExecutionState.COMPLETED))
    props = find_proposals(exs, {"meeting-preparation"})
    assert len(props) == 1 and props[0].count == 3
    assert props[0].status == "proposed" and props[0].evidence
    # already-covered workflows are not proposed
    assert find_proposals(exs, {props[0].name}) == []


def test_discovery_yaml_renders():
    from skills.discovery import SkillProposal, render_skill_yaml
    y = render_skill_yaml(SkillProposal(id="a", name="research-review",
                                        description="d", agent="research",
                                        required_tools=["web", "notes"]))
    assert "name: research-review" in y and "version:" in y and "web" in y


def test_approved_proposal_registers_as_skill(tmp_path):
    """The exact artifact the approve endpoint writes must load as a skill."""
    from runtime.schemas import ExecutionState
    from skills.discovery import find_proposals, render_skill_yaml
    from skills.registry import SkillRegistry
    exs = [Execution(id=str(i), user_request="summarize this research paper please",
                     agent="research", state=ExecutionState.COMPLETED) for i in range(3)]
    (proposal,) = find_proposals(exs, set())
    target = tmp_path / f"discovered-{proposal.name}" / "skill.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(render_skill_yaml(proposal))
    reg = SkillRegistry(skills_dir=str(tmp_path))
    assert proposal.name in {s.name for s in reg.list()}
    assert reg.match(f"please run {proposal.name} now") is not None


def test_timeline_builds_ordered_steps():
    from runtime.timeline import build_timeline
    from audit.service import AuditService  # noqa: F401  (schema shape reference)
    from datetime import datetime, timezone

    class E:
        action, agent, resource, permission, reason, status = "", "", "", "", "", ""
        timestamp = datetime.now(timezone.utc)

    def ev(action, status="ok", permission="", reason="r"):
        e = E()
        e.action, e.status, e.permission, e.reason = action, status, permission, reason
        return e

    ex = Execution(id="e1", user_request="hi", agent="research", skill="research",
                   state=ExecutionState.COMPLETED)
    tl = build_timeline(ex, [ev("intent_classified"), ev("memory_read"),
                             ev("agent_started"), ev("calendar.read", permission="ALLOW"),
                             ev("approval_requested", status="pending"),
                             ev("agent_finished")])
    labels = [s["label"] for s in tl]
    assert labels[0] == "USER REQUEST" and labels[-1] == "COMPLETED"
    for want in ("PLANNER", "MEMORY RETRIEVAL", "AGENT", "POLICY CHECK", "APPROVAL", "RESULT"):
        assert want in labels, labels
    assert not any("reasoning" in str(s).lower() for s in tl)


def test_demo_seed_data_is_marked():
    from demo.seed_data import DEMO_EVENTS, DEMO_MEMORIES, DEMO_NOTES, DEMO_SOURCE
    assert DEMO_SOURCE == "demo-seed" and len(DEMO_MEMORIES) >= 4
    assert all(c.startswith("Demo ") or "Demo" in c for _, c, _ in DEMO_MEMORIES)
    assert all(e["id"].startswith("demo-") for e in DEMO_EVENTS)
    assert all(n["id"].startswith("demo-") for n in DEMO_NOTES)


def test_model_config_validation():
    from core.config import Settings
    assert Settings().validate_model_config() == []  # mock always valid
    bad = Settings(model_provider="wat")
    assert any("Unknown MODEL_PROVIDER" in p for p in bad.validate_model_config())
    nokey = Settings(model_provider="openai_compatible", openai_api_key="",
                     openrouter_api_key="")
    assert any("API key" in p for p in nokey.validate_model_config())
