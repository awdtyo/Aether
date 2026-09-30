"""Model provider abstraction. App code never touches a vendor SDK directly.

OpenRouter (or any OpenAI-compatible endpoint) is reached through
OpenAICompatibleProvider with the configured base URL — no per-vendor HTTP
code. Reasoning traces returned by the endpoint are never surfaced: only the
final message content is exposed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

log = logging.getLogger("aether.models")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str


# -- error taxonomy (all messages are safe: never include keys/headers) ----


class ProviderError(Exception):
    """Base class. `retryable` hints whether the caller may retry."""


class ProviderConfigError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderModelError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class _EmptyResponse(Exception):
    """Internal: model returned no usable content (transient — worth one retry)."""


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
    """Any OpenAI-compatible chat-completions endpoint (OpenRouter, Nebius, NVIDIA, ...)."""
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0,
                 extra_headers: dict[str, str] | None = None, max_retries: int = 1):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.max_retries = max(0, max_retries)

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        headers.update(self.extra_headers)
        return headers

    def _check_config(self, model: str) -> None:
        if not self.api_key:
            raise ProviderConfigError(
                "OpenRouter API key is not configured. "
                "Set OPENAI_API_KEY (or OPENROUTER_API_KEY) in the environment.")
        if not self.base_url:
            raise ProviderConfigError("Model base URL is not configured. Set OPENAI_BASE_URL.")
        if not model:
            raise ProviderConfigError("Model name is not configured. Set MODEL_NAME.")

    @staticmethod
    def _extract_text(message: dict[str, Any], model: str) -> str:
        """Final message content only. Reasoning metadata is deliberately dropped."""
        content = message.get("content", "")
        if isinstance(content, list):  # multipart content blocks
            content = "".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") != "reasoning")
        text = content if isinstance(content, str) else ""
        if not text.strip():
            raise _EmptyResponse(f"empty content (model={model})")
        return text

    async def chat(self, messages: list[ChatMessage], model: str, **kw) -> ChatResponse:
        import httpx

        self._check_config(model)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "temperature": kw.get("temperature", 0.3),
        }
        if kw.get("max_tokens") is not None:
            payload["max_tokens"] = kw["max_tokens"]
        if kw.get("response_format") is not None:
            payload["response_format"] = kw["response_format"]
        timeout = kw.get("timeout", self.timeout)
        host = self.base_url.split("://")[-1].split("/")[0]  # never log keys/headers/body
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{self.base_url}/chat/completions",
                                             headers=self._headers(), json=payload)
            except httpx.TimeoutException as e:
                log.warning("model timeout host=%s model=%s after=%ss", host, model, timeout)
                raise ProviderTimeoutError(
                    f"Model request timed out after {timeout}s without crashing the runtime.") from e
            except httpx.ConnectError as e:
                log.warning("model unreachable host=%s model=%s", host, model)
                raise ProviderUnavailableError(
                    f"Model provider at {self.base_url} is unreachable.") from e
            except httpx.HTTPError as e:
                log.warning("model transport error host=%s model=%s err=%s",
                            host, model, type(e).__name__)
                raise ProviderUnavailableError(f"Model provider transport error: {type(e).__name__}.") from e
            ms = (time.monotonic() - t0) * 1000
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                last_err = self._status_error(resp, model)
                log.info("model retry host=%s model=%s http=%s attempt=%s",
                         host, model, resp.status_code, attempt + 1)
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code != 200:
                log.warning("model error host=%s model=%s http=%s",
                            host, model, resp.status_code)
                raise self._status_error(resp, model)
            try:
                data = resp.json()
                message = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError) as e:
                raise ProviderError("Provider returned a malformed response.") from e
            try:
                text = self._extract_text(message, model)
            except _EmptyResponse:
                if attempt < self.max_retries:
                    log.info("model empty response, retrying host=%s model=%s", host, model)
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise ProviderError(
                    f"Provider returned an empty response (model={model}).") from None
            log.info("model ok host=%s model=%s ms=%.0f", host, model, ms)
            return ChatResponse(text=text, model=model, provider="openai_compatible")
        raise last_err or ProviderUnavailableError("Model provider unavailable after retries.")

    @staticmethod
    def _status_error(resp: Any, model: str) -> ProviderError:
        code = resp.status_code
        try:
            detail = (resp.json().get("error") or {}).get("message", "")
        except Exception:
            detail = ""
        suffix = f" Detail: {detail[:200]}" if detail else ""
        if code in (401, 403):
            return ProviderAuthError("Provider authentication failed. Check the API key." + suffix)
        if code == 404:
            return ProviderModelError(
                f"Model '{model}' not found at this endpoint. Check MODEL_NAME." + suffix)
        if code == 429:
            return ProviderRateLimitError("Provider rate limit hit (retryable)." + suffix)
        if code and 500 <= code < 600:
            return ProviderUnavailableError(f"Provider server error (HTTP {code}, retryable)." + suffix)
        return ProviderError(f"Provider request failed (HTTP {code})." + suffix)

    async def generate_json(self, messages: list[ChatMessage], model: str,
                            schema: type[BaseModel] | Any, **kw) -> Any:
        """Structured output with Pydantic validation. Falls back from
        response_format to fenced-JSON extraction when the endpoint ignores it.
        Never returns unvalidated model JSON."""
        try:
            raw = await self.chat(messages, model, response_format={"type": "json_object"}, **kw)
            text = raw.text
        except ProviderError:
            raise
        try:
            data = json.loads(text)
        except ValueError:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
            if not m:
                raise ProviderError("Model did not return parseable JSON.")
            data = json.loads(m.group(1))
        try:
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_validate(data)
            return TypeAdapter(schema).validate_python(data)
        except Exception as e:
            raise ProviderError(f"Model JSON failed validation: {e}") from e


T = TypeVar("T")
