"""Private-memory infrastructure tests. Everything uses tmp dirs —
never the developer's real ~/.aether."""
import re

import pytest


def _settings():
    from core.config import get_settings
    return get_settings()


def test_default_data_dir_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AETHER_DATA_DIR", raising=False)
    from core.config import Settings
    s = Settings()
    assert s.data_dir() == tmp_path / ".aether"
    assert (tmp_path / ".aether").is_dir()


def test_custom_data_dir_created(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "nested"
    monkeypatch.setenv("AETHER_DATA_DIR", str(target))
    assert _settings().data_dir() == target
    assert target.is_dir()
    assert _settings().memory_db_path().parent.is_dir()


def test_explicit_database_url_wins(monkeypatch, tmp_path):
    from database.db import resolve_database_url
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////tmp/x.db")
    assert resolve_database_url() == "sqlite+aiosqlite:////tmp/x.db"


def test_default_url_lives_in_data_dir(tmp_path):
    from database.db import resolve_database_url
    url = resolve_database_url()
    assert url == _settings().memory_db_url()
    assert url.endswith("memory/memory.db") and str(tmp_path) in url
    assert "/backend/" not in url and "/Aether/" not in url.split("memory")[0]


@pytest.mark.asyncio
async def test_memory_persists_across_restarts(tmp_path):
    from memory.schemas import MemoryCreate, MemoryType
    # build explicitly: two independent service instances, one file
    from database.db import build_session_factory
    from database.models import Base as ModelsBase
    from memory.service import MemoryService
    from sqlalchemy.ext.asyncio import create_async_engine
    url = f"sqlite+aiosqlite:///{tmp_path}/m.db"
    engine = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
    await engine.dispose()
    a = MemoryService(session_factory=build_session_factory(url))
    m = await a.create(MemoryCreate(type=MemoryType.FACT, content="Persistence probe value."))
    b = MemoryService(session_factory=build_session_factory(url))  # "restart"
    got = await b.get(m.id)
    assert got is not None and got.content == "Persistence probe value."
    assert (await b.search("persistence probe"))[0].id == m.id
    assert await b.list(types=[MemoryType.FACT])


@pytest.mark.asyncio
async def test_import_validated_and_idempotent(tmp_path):
    from demo.seed_memory import run_import
    from memory.service import MemoryService
    from database.db import build_session_factory
    from database.models import Base as ModelsBase
    from sqlalchemy.ext.asyncio import create_async_engine
    url = f"sqlite+aiosqlite:///{tmp_path}/m.db"
    engine = create_async_engine(url, echo=False, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
    await engine.dispose()
    svc = MemoryService(session_factory=build_session_factory(url))
    f = tmp_path / "personal_memory.yaml"
    f.write_text("user:\n  name: Test Persona\ninterests:\n  - stargazing\n"
                 "preferences:\n  communication_style: brief\ngoals:\n  - Nap more.\n")
    first = await run_import(svc, f)
    assert first == {"added": 4, "skipped": 0}
    second = await run_import(svc, f)
    assert second == {"added": 0, "skipped": 4}
    srcs = {m.source for m in await svc.list(limit=50)}
    assert {"user_profile", "user_preference", "user_input"} <= srcs


def test_import_rejects_malformed(tmp_path):
    from demo.seed_memory import load_personal_memory_file
    bad = tmp_path / "bad.yaml"
    bad.write_text("user: [unclosed\n  broken: : :")
    with pytest.raises(ValueError, match="malformed|invalid"):
        load_personal_memory_file(bad)
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text("memories:\n  - type: BOGUS\n    content: x\n")
    with pytest.raises(ValueError, match="invalid memory type"):
        from demo.seed_memory import to_entries
        to_entries(load_personal_memory_file(wrong))


def test_demo_and_template_are_fictional():
    import re
    from demo.seed_data import DEMO_MEMORIES
    from pathlib import Path
    secret = re.compile(r"sk-(or|live|ant)-|ghp_|AKIA|@")
    for _, content, _ in DEMO_MEMORIES:
        assert not secret.search(content), content
        assert "Demo" in content or "demo" in content
    template = Path("data/seed/memory.example.yaml")
    assert template.exists()
    text = template.read_text()
    assert not secret.search(text)
    assert "Demo User" in text and "FICTIONAL" in text


def test_no_static_file_serving_and_no_data_routes():
    from main import app
    mounts = [r for r in app.routes if type(r).__name__ == "Mount"]
    assert mounts == []
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any(".aether" in p or "personal_memory" in p for p in paths)


def test_docker_config_never_bakes_private_data():
    from pathlib import Path
    compose = Path("docker-compose.yml").read_text()
    assert "AETHER_DATA_DIR" in compose and "/data/aether" in compose
    backend_dockerfile = Path("backend/Dockerfile").read_text()
    assert ".aether" not in backend_dockerfile and "aether.db" not in backend_dockerfile
    di = Path("backend/.dockerignore")
    assert di.exists()
    assert "*.db" in di.read_text() and ".env" in di.read_text()


def test_discovery_writes_outside_repo(tmp_path, monkeypatch):
    from core.config import get_settings
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "priv"))
    get_settings.cache_clear()
    try:
        target = get_settings().skills_data_dir() / "discovered-x" / "skill.yaml"
        assert str(target).startswith(str(tmp_path))
        assert "Aether" not in str(target) or str(tmp_path) in str(target)
    finally:
        get_settings.cache_clear()
