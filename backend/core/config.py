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
    openai_base_url: str = "https://api.studio.nebius.com/v1"
    openai_api_key: str = ""
    model_fast: str = "nemotron-fast"
    model_standard: str = "nemotron-standard"
    model_reasoning: str = "nemotron-reasoning"
    model_multimodal: str = "nemotron-multimodal"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
