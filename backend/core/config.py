"""AETHER core configuration. All secrets come from environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str:
    """Locate .env regardless of process CWD (repo root or backend/)."""
    here = Path(__file__).resolve()
    for candidate in (Path.cwd() / ".env",
                      here.parent.parent.parent / ".env",  # repo root
                      here.parent.parent / ".env"):  # backend/
        if candidate.exists():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_env_file(), extra="ignore")

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
    # Provider behavior knobs. max_tokens must leave headroom for Nemotron's
    # reasoning tokens (which count toward the completion budget).
    model_temperature: float = 0.3
    model_max_tokens: int = 4096
    model_timeout_s: float = 60.0

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Local/private AETHER data directory. Do not commit personal memory data.
    aether_data_dir: str = "~/.aether"

    # Controlled demo environment (deterministic sample data, no credentials).
    demo_mode: bool = False

    # -- private data directory ------------------------------------------
    def data_dir(self) -> Path:
        """Expanded private data dir, created on demand (idempotent)."""
        path = Path(self.aether_data_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def display_data_dir(self) -> str:
        """Human label with ~ (never leaks absolute home paths to the UI)."""
        path = Path(self.aether_data_dir).expanduser()
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def memory_db_path(self) -> Path:
        mem = self.data_dir() / "memory"
        mem.mkdir(parents=True, exist_ok=True)
        return mem / "memory.db"

    def memory_db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.memory_db_path()}"

    def skills_data_dir(self) -> Path:
        skills = self.data_dir() / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        return skills

    def validate_model_config(self) -> list[str]:
        """Startup validation. Returns human-readable problems (empty = ok).

        Mock mode is always valid. Remote providers stay alive without a key
        so the API boots; executions then fail cleanly per-call."""
        problems: list[str] = []
        if self.model_provider == "mock":
            return problems
        if self.model_provider not in ("openai_compatible", "nebius", "openrouter"):
            problems.append(
                f"Unknown MODEL_PROVIDER={self.model_provider!r}; "
                "expected mock | openai_compatible | nebius. Using local mock.")
            return problems
        if not (self.openai_api_key or self.openrouter_api_key):
            problems.append(
                "No model API key configured. Set OPENAI_API_KEY (or "
                "OPENROUTER_API_KEY); model calls will fail until then.")
        if not self.openai_base_url:
            problems.append("OPENAI_BASE_URL is empty.")
        if not self.model_name:
            problems.append("MODEL_NAME is empty.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
