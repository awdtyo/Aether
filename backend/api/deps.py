"""Shared singletons: one store/registry per process (simple, testable)."""
from __future__ import annotations

from audit.service import AuditService
from core.config import get_settings
from memory.service import MemoryService
from models.router import ModelRouter
from policies.engine import PolicyEngine
from runtime.orchestrator import Deps, Orchestrator
from runtime.store import ExecutionStore
from skills.registry import SkillRegistry
from tools.registry import ToolRegistry

_settings = get_settings()
_engine = None
try:
    from database.db import get_session_factory
    _engine = get_session_factory  # factory getter; resolved lazily
    _factory = get_session_factory()
    _db_ok = True
except Exception:
    _factory = None
    _db_ok = False

memory = MemoryService(session_factory=_factory)
audit = AuditService(session_factory=_factory)
policy = PolicyEngine()
tools = ToolRegistry(policy=policy)
router = ModelRouter()
store = ExecutionStore()
# Curated repo skills + private user skills (approved discoveries live outside git).
skills = SkillRegistry(skills_dir="skills",
                       extra_dirs=[str(_settings.skills_data_dir())])
orchestrator = Orchestrator(store, skills, Deps(memory=memory, tools=tools, audit=audit,
                                                router=router, policy=policy))

db_available = _db_ok
