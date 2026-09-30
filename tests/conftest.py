import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest


@pytest.fixture(autouse=True)
def _hermetic_model_env(monkeypatch):
    """Tests must be deterministic and offline: never inherit a real .env
    model configuration from the developer's machine."""
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
