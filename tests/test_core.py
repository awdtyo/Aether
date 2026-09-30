"""Memory + runtime + orchestrator tests (asyncio)."""
import pytest

from memory.schemas import MemoryCreate, MemoryType
from memory.service import MemoryService, embed, worth_persisting
from runtime.store import ExecutionStore
from runtime.schemas import ExecutionState


def test_embed_deterministic():
    assert embed("hello world") == embed("hello world")
    assert len(embed("x")) == 256


def test_worth_persisting_gate():
    assert not worth_persisting("hi")
    assert not worth_persisting("thanks!")
    assert worth_persisting("I decided to use React for the AETHER frontend project")
    assert worth_persisting("My goal is to finish the thesis by December with weekly reviews " * 3)


async def _svc():
    return MemoryService()


@pytest.mark.asyncio
async def test_memory_crud_and_search():
    svc = await _svc()
    m = await svc.create(MemoryCreate(type=MemoryType.DECISION,
                                      content="The user chose React for the AETHER frontend project."))
    assert m.id
    got = await svc.get(m.id)
    assert got and got.content.startswith("The user chose")
    res = await svc.search("which frontend framework did the user choose?")
    assert res and res[0].id == m.id
    upd = await svc.update(m.id, __import__("memory.schemas", fromlist=["MemoryUpdate"]).MemoryUpdate(confidence=0.99))
    assert upd.confidence == 0.99
    assert await svc.delete(m.id) is True
    assert await svc.get(m.id) is None


@pytest.mark.asyncio
async def test_memory_type_filter():
    svc = await _svc()
    await svc.create(MemoryCreate(type=MemoryType.GOAL, content="Goal: run a marathon in the project timeline"))
    await svc.create(MemoryCreate(type=MemoryType.FACT, content="Fact: the sky appears blue at noon"))
    res = await svc.search("marathon goal", types=[MemoryType.GOAL])
    assert all(r.type == MemoryType.GOAL for r in res)


def test_runtime_transitions():
    store = ExecutionStore()
    ex = store.create("hello")
    store.transition(ex, ExecutionState.PLANNING)
    store.transition(ex, ExecutionState.EXECUTING)
    try:
        store.transition(ex, ExecutionState.CREATED)
        assert False, "should have raised"
    except ValueError:
        pass


@pytest.mark.asyncio
async def test_tool_policy_gate_and_sandbox(tmp_path):
    from policies.engine import PolicyEngine
    from tools.registry import ToolRegistry

    reg = ToolRegistry(policy=PolicyEngine())
    # traversal attempt must not escape workspace
    import core.config as cfg
    s = cfg.get_settings()
    s.workspace_root = str(tmp_path)
    res, verdict = await reg.run("personal", "filesystem", "write", {"content": "x"},
                                 "../../evil.txt", audit=None, execution_id="t")
    assert verdict.decision.value == "APPROVAL_REQUIRED"  # outside Projects/Research
    res2, v2 = await reg.run("personal", "filesystem", "read", {}, "/Private/x",
                             audit=None, execution_id="t")
    assert v2.decision.value == "DENY" and not res2.ok


@pytest.mark.asyncio
async def test_orchestrator_demo_flows():
    from audit.service import AuditService
    from models.router import ModelRouter
    from policies.engine import PolicyEngine
    from runtime.orchestrator import Deps, Orchestrator
    from skills.registry import SkillRegistry
    from tools.registry import ToolRegistry

    mem, tools = MemoryService(), ToolRegistry(policy=PolicyEngine())
    orch = Orchestrator(ExecutionStore(), SkillRegistry(skills_dir="../skills"),
                        Deps(memory=mem, tools=tools, audit=AuditService(),
                             router=ModelRouter(), policy=PolicyEngine()))
    ex1 = await orch.handle("Prepare my research meeting for tomorrow.")
    assert ex1.state == ExecutionState.COMPLETED and ex1.agent == "research"
    ex2 = await orch.handle("Send the brief to my research group.")
    assert ex2.state == ExecutionState.WAITING_FOR_PERMISSION
    ex3 = await orch.resume_after_approval(ex2.id, True)
    assert ex3 is not None and ex3.state == ExecutionState.COMPLETED
