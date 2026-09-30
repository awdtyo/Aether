"""ModelRouter: picks fast/standard/reasoning/multimodal by task signals.

Model names live in env config — never hard-coded across the app.
`MODEL_NAME` is the canonical default; MODEL_FAST/_STANDARD/_REASONING/
_MULTIMODAL are optional per-tier overrides (empty = use MODEL_NAME).

Architecture stays: Agent -> ModelRouter -> ModelProvider -> endpoint,
so OpenRouter, Nebius, or a local model can be swapped without touching agents.
"""
from __future__ import annotations

from core.config import get_settings
from models.providers import ChatMessage, ChatResponse, MockProvider, OpenAICompatibleProvider


class ModelRouter:
    def __init__(self):
        s = get_settings()
        key = s.openai_api_key or s.openrouter_api_key
        self.default_model = s.model_name
        self.models = {
            tier: (getattr(s, f"model_{tier}") or s.model_name)
            for tier in ("fast", "standard", "reasoning", "multimodal")
        }
        self.temperature = s.model_temperature
        self.max_tokens = s.model_max_tokens
        if s.model_provider in ("openai_compatible", "nebius", "openrouter"):
            extra: dict[str, str] = {}
            if s.openrouter_http_referer:
                extra["HTTP-Referer"] = s.openrouter_http_referer
            if s.openrouter_x_title:
                extra["X-Title"] = s.openrouter_x_title
            self.provider = OpenAICompatibleProvider(
                s.openai_base_url, key, timeout=s.model_timeout_s,
                extra_headers=extra)
        else:
            self.provider = MockProvider()

    def status(self) -> dict:
        """Safe for UI exposure: no keys, no headers, no secrets."""
        configured = self.provider.name != "mock" and bool(
            getattr(self.provider, "api_key", ""))
        return {"provider": "OpenRouter" if "openrouter" in getattr(
                    self.provider, "base_url", "") else self.provider.name,
                "endpoint": getattr(self.provider, "base_url", "local"),
                "model": self.default_model,
                "state": "Connected" if configured else "Not Configured"
                if self.provider.name != "mock" else "Local mock"}

    async def generate_structured(self, prompt: str, schema, system: str,
                                  tier: str = "fast"):
        """Model-driven structured decisions, Pydantic-validated.

        Raises ProviderError when the provider cannot do structured output
        (e.g. local mock) — callers must fall back to deterministic rules.
        The result only ever selects names; it never authorizes anything."""
        from models.providers import ProviderError
        fn = getattr(self.provider, "generate_json", None)
        if fn is None:
            raise ProviderError("Provider does not support structured output.")
        from models.providers import ChatMessage
        return await fn([ChatMessage(role="system", content=system),
                         ChatMessage(role="user", content=prompt)],
                        model=self.models.get(tier, self.default_model),
                        schema=schema, temperature=0.1,
                        max_tokens=self.max_tokens)

    def pick_tier(self, task: str, multimodal: bool = False, complex: bool = False) -> str:
        if multimodal:
            return "multimodal"
        if complex or len(task) > 600:
            return "reasoning"
        if len(task) < 200:
            return "fast"
        return "standard"

    async def generate(self, prompt: str, tier: str | None = None,
                       system: str = "You are AETHER, a precise personal AI OS.",
                       context: str = "") -> ChatResponse:
        from core.config import get_settings as _gs
        tier = tier or self.pick_tier(prompt)
        msgs = [ChatMessage(role="system", content=system)]
        if context:
            msgs.append(ChatMessage(role="system", content=f"Relevant memory:\n{context[:3000]}"))
        msgs.append(ChatMessage(role="user", content=prompt))
        return await self.provider.chat(
            msgs, model=self.models.get(tier, self.default_model),
            temperature=self.temperature, max_tokens=self.max_tokens)
