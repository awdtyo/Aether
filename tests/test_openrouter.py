"""OpenRouter / Nemotron integration tests. No real keys, no network (httpx stubbed)."""
import json
from contextlib import contextmanager

import pytest

import httpx


@contextmanager
def openrouter_env(monkeypatch, **overrides):
    env = {"MODEL_PROVIDER": "openai_compatible",
           "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
           "OPENAI_API_KEY": "test-key",
           "MODEL_NAME": "nvidia/nemotron-3.5-lightning"}
    env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from core.config import get_settings
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    """Stand-in for httpx.AsyncClient. Queue responses or exceptions."""
    instances: list = []

    def __init__(self, *a, **kw):
        self.calls = []
        self.script: list = []
        FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_http(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    return FakeClient


def ok_payload(text="Hello from Nemotron", model="nvidia/nemotron-3.5-lightning"):
    return {"choices": [{"message": {"content": text,
                                     "reasoning_content": "private chain of thought"}}],
            "model": model}


# -- configuration -------------------------------------------------------


def test_settings_load_openrouter_config(monkeypatch):
    with openrouter_env(monkeypatch):
        from core.config import get_settings
        s = get_settings()
        assert s.model_provider == "openai_compatible"
        assert s.openai_base_url == "https://openrouter.ai/api/v1"
        assert s.model_name == "nvidia/nemotron-3.5-lightning"


def test_alternate_model_id_needs_no_code_change(monkeypatch):
    with openrouter_env(monkeypatch, MODEL_NAME="nvidia/nemotron-3-ultra-550b-a55b"):
        from models.router import ModelRouter
        r = ModelRouter()
        assert r.default_model == "nvidia/nemotron-3-ultra-550b-a55b"
        assert set(r.models.values()) == {"nvidia/nemotron-3-ultra-550b-a55b"}


def test_openrouter_key_alias(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "alias-key")
    monkeypatch.setenv("MODEL_NAME", "nvidia/nemotron-3.5-lightning")
    from core.config import get_settings
    get_settings.cache_clear()
    try:
        from models.router import ModelRouter
        r = ModelRouter()
        assert r.provider.api_key == "alias-key"
    finally:
        get_settings.cache_clear()


# -- provider request shape ----------------------------------------------


@pytest.mark.asyncio
async def test_provider_request_shape_and_reasoning_dropped(monkeypatch, fake_http):
    from models.providers import ChatMessage, OpenAICompatibleProvider
    p = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "test-key",
                                 extra_headers={"X-Title": "AETHER"})
    FakeClient.instances.clear()
    cli = FakeClient()
    cli.script.append(FakeResponse(200, ok_payload()))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
    resp = await p.chat([ChatMessage(role="system", content="sys"),
                         ChatMessage(role="user", content="hi")],
                        model="nvidia/nemotron-3.5-lightning",
                        temperature=0.3, max_tokens=64)
    assert resp.text == "Hello from Nemotron"  # reasoning_content never surfaced
    call = cli.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["headers"]["X-Title"] == "AETHER"
    assert call["json"]["model"] == "nvidia/nemotron-3.5-lightning"
    assert call["json"]["messages"][0]["role"] == "system"
    assert call["json"]["temperature"] == 0.3
    assert call["json"]["max_tokens"] == 64


# -- error taxonomy --------------------------------------------------------


@pytest.mark.asyncio
async def test_error_mapping(monkeypatch, fake_http):
    from models.providers import (ChatMessage, OpenAICompatibleProvider,
                                  ProviderAuthError, ProviderConfigError,
                                  ProviderModelError, ProviderRateLimitError,
                                  ProviderTimeoutError, ProviderUnavailableError)
    msgs = [ChatMessage(role="user", content="hi")]

    p = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "")
    with pytest.raises(ProviderConfigError, match="not configured"):
        await p.chat(msgs, model="m")

    async def run(item, **kw):
        p = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "k", max_retries=0, **kw)
        cli = FakeClient()
        cli.script.append(item)
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
        return await p.chat(msgs, model="nvidia/nemotron-3.5-lightning")

    with pytest.raises(ProviderAuthError):
        await run(FakeResponse(401, {"error": {"message": "bad key"}}))
    with pytest.raises(ProviderModelError, match="MODEL_NAME"):
        await run(FakeResponse(404, {"error": {"message": "not found"}}))
    with pytest.raises(ProviderRateLimitError):
        await run(FakeResponse(429, {}))
    with pytest.raises(ProviderUnavailableError):
        await run(FakeResponse(503, {}))
    with pytest.raises(ProviderTimeoutError):
        await run(httpx.TimeoutException("slow"))
    with pytest.raises(ProviderUnavailableError):
        await run(httpx.ConnectError("down"))


@pytest.mark.asyncio
async def test_retry_then_success(monkeypatch, fake_http):
    from models.providers import ChatMessage, OpenAICompatibleProvider
    p = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "k", max_retries=1)
    cli = FakeClient()
    cli.script.extend([FakeResponse(429, {}), FakeResponse(200, ok_payload("recovered"))])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
    resp = await p.chat([ChatMessage(role="user", content="hi")],
                        model="nvidia/nemotron-3.5-lightning")
    assert resp.text == "recovered" and len(cli.calls) == 2


# -- structured output -------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_json_validated(monkeypatch, fake_http):
    from models.providers import ChatMessage, OpenAICompatibleProvider, ProviderError
    from pydantic import BaseModel

    class Intent(BaseModel):
        agent: str
        confidence: float

    async def run(text):
        p = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "k", max_retries=0)
        cli = FakeClient()
        cli.script.append(FakeResponse(200, ok_payload(text)))
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
        return await p.generate_json([ChatMessage(role="user", content="x")],
                                     model="m", schema=Intent)

    good = await run('{"agent": "research", "confidence": 0.9}')
    assert good.agent == "research"
    fenced = await run('```json\n{"agent": "planning", "confidence": 0.5}\n```')
    assert fenced.agent == "planning"
    with pytest.raises(ProviderError):
        await run('{"agent": "research"}')  # missing field -> validation error


# -- mock intact / status ------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_provider_still_works():
    from models.providers import ChatMessage, MockProvider
    r = await MockProvider().chat([ChatMessage(role="user", content="hello")], model="m")
    assert r.provider == "mock" and r.text


def test_status_exposes_no_secrets(monkeypatch):
    with openrouter_env(monkeypatch):
        from models.router import ModelRouter
        st = ModelRouter().status()
        assert st["state"] == "Connected"
        assert "test-key" not in json.dumps(st)
        assert "Authorization" not in json.dumps(st)


# -- runtime path with stubbed network ------------------------------------------


def _orch(monkeypatch):
    from audit.service import AuditService
    from memory.service import MemoryService
    from models.router import ModelRouter
    from policies.engine import PolicyEngine
    from runtime.orchestrator import Deps, Orchestrator
    from runtime.store import ExecutionStore
    from skills.registry import SkillRegistry
    from tools.registry import ToolRegistry
    mem, tools = MemoryService(), ToolRegistry(policy=PolicyEngine())
    return Orchestrator(ExecutionStore(), SkillRegistry(skills_dir="skills"),
                        Deps(memory=mem, tools=tools, audit=AuditService(),
                             router=ModelRouter(), policy=PolicyEngine()))


@pytest.mark.asyncio
async def test_runtime_via_openrouter_stub(monkeypatch, fake_http):
    from runtime.schemas import ExecutionState
    with openrouter_env(monkeypatch):
        orch = _orch(monkeypatch)
        cli = FakeClient()
        cli.script.append(FakeResponse(200, ok_payload("Nemotron brief: agenda, risks, actions.")))
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
        ex = await orch.handle("Prepare my research meeting for tomorrow.")
        assert ex.state == ExecutionState.COMPLETED
        assert ex.skill == "meeting-preparation" and ex.agent == "research"
        assert "Nemotron brief" in (ex.result or "")


@pytest.mark.asyncio
async def test_llm_request_for_protected_action_still_gated(monkeypatch, fake_http):
    from runtime.schemas import ExecutionState
    with openrouter_env(monkeypatch):
        orch = _orch(monkeypatch)
        cli = FakeClient()
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: cli)
        ex = await orch.handle("Send the brief to my research group.")
        assert ex.state == ExecutionState.WAITING_FOR_PERMISSION
        denied = await orch.resume_after_approval(ex.id, False)
        assert denied is not None and denied.state == ExecutionState.FAILED
        events = await orch.deps.audit.list(execution_id=ex.id, limit=50)
        actions = {e.action for e in events}
        assert "approval_requested" in actions and "approval_denied" in actions
