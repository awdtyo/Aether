import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest


@pytest.fixture(autouse=True)
def _hermetic_model_env(monkeypatch, tmp_path):
    """Tests must be deterministic and offline: never inherit a real .env
    model configuration, and never touch the developer's real ~/.aether."""
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "aether-test-data"))
    from core.config import get_settings
    from database import db as _db
    get_settings.cache_clear()
    _db.reset_db_state()
    yield
    get_settings.cache_clear()
    _db.reset_db_state()
