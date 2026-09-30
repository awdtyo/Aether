"""Model provider abstraction. App code never touches a vendor SDK directly."""
from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str


class ModelProvider:
    name = "base"

    async def chat(self, messages: list[ChatMessage], model: str, **kw) -> ChatResponse:
        raise NotImplementedError


class MockProvider(ModelProvider):
    """Deterministic local provider for dev/test with zero credentials."""
    name = "mock"

    async def chat(self, messages: list[ChatMessage], model: str, **kw) -> ChatResponse:
        last = messages[-1].content if messages else ""
        return ChatResponse(
            text=f"[mock:{model}] Understood. Key point of your request: '{last[:160]}'. "
                 "AETHER runtime handled this locally (no external LLM call).",
            model=model, provider="mock")


class OpenAICompatibleProvider(ModelProvider):
    """Any OpenAI-compatible chat-completions endpoint (Nebius, NVIDIA, OpenAI, Ollama)."""
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def chat(self, messages: list[ChatMessage], model: str, **kw) -> ChatResponse:
        import httpx

        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": model,
                      "messages": [m.model_dump() for m in messages],
                      "temperature": kw.get("temperature", 0.3)})
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"]
        return ChatResponse(text=text, model=model, provider="openai_compatible")
