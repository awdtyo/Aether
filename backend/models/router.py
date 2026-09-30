"""ModelRouter: picks fast/standard/reasoning/multimodal by task signals.

Model names live in env config — never hard-coded across the app.
"""
from __future__ import annotations

from core.config import get_settings
from models.providers import ChatMessage, ChatResponse, MockProvider, OpenAICompatibleProvider


class ModelRouter:
    def __init__(self):
        s = get_settings()
        if s.model_provider in ("openai_compatible", "nebius") and s.openai_api_key:
            self.provider = OpenAICompatibleProvider(s.openai_base_url, s.openai_api_key)
        else:
            self.provider = MockProvider()
        self.models = {"fast": s.model_fast, "standard": s.model_standard,
                       "reasoning": s.model_reasoning, "multimodal": s.model_multimodal}

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
        tier = tier or self.pick_tier(prompt)
        msgs = [ChatMessage(role="system", content=system)]
        if context:
            msgs.append(ChatMessage(role="system", content=f"Relevant memory:\n{context[:3000]}"))
        msgs.append(ChatMessage(role="user", content=prompt))
        return await self.provider.chat(msgs, model=self.models.get(tier, self.models["standard"]))
