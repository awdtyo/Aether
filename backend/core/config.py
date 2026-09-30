"""AETHER core configuration. All secrets come from environment."""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AETHER"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./aether.db"

    workspace_root: str = "/tmp/aether_workspace"
    git_allowlist: str = "/tmp/aether_workspace"

    model_provider: str = "mock"  # mock | openai_compatible | nebius
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str = ""
    # Provider-specific alias; canonical secret internally is openai_api_key.
    openrouter_api_key: str = ""
    # Canonical model id (e.g. nvidia/nemotron-3.5-lightning). Tier variables
    # below are optional per-tier overrides; empty means "use model_name".
    model_name: str = "nvidia/nemotron-3.5-lightning"
    model_fast: str = ""
    model_standard: str = ""
    model_reasoning: str = ""
    model_multimodal: str = ""
    # Optional OpenRouter metadata headers (sent only when set).
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "AETHER"
    # Provider behavior knobs.
    model_temperature: float = 0.3
    model_max_tokens: int = 1024
    model_timeout_s: float = 60.0

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
