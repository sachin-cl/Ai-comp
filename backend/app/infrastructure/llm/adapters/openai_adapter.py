"""OpenAI Chat Completions adapter (httpx; no SDK dependency)."""
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.errors import LLMError
from app.domain.ports.llm_gateway import ChatMessage, LLMResult
from app.domain.value_objects import TokenUsage
from app.infrastructure.llm.base import ProviderAdapter, register_provider

BASE_URL = "https://api.openai.com/v1"


@register_provider("openai")
class OpenAIAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE_URL)

    def _headers(self) -> dict[str, str]:
        key = get_settings().openai_api_key
        if not key:
            raise LLMError("OPENAI_API_KEY is not configured")
        return {"Authorization": f"Bearer {key}"}

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
        json_mode: bool = False,
    ) -> LLMResult:
        body: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        resp = await self._client.post(
            "/chat/completions", json=body, headers=self._headers(), timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResult(
            text=data["choices"][0]["message"]["content"] or "",
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> AsyncIterator[LLMResult | str]:
        body = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        start = time.perf_counter()
        usage = TokenUsage()
        full: list[str] = []
        async with self._client.stream(
            "POST", "/chat/completions", json=body, headers=self._headers(), timeout=timeout
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("usage"):
                    usage = TokenUsage(
                        prompt_tokens=chunk["usage"].get("prompt_tokens", 0),
                        completion_tokens=chunk["usage"].get("completion_tokens", 0),
                    )
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        full.append(delta)
                        yield delta
        yield LLMResult(
            text="".join(full),
            usage=usage,
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def embed(self, texts: list[str], *, model: str, timeout: float) -> list[list[float]]:
        resp = await self._client.post(
            "/embeddings",
            json={"model": model, "input": texts},
            headers=self._headers(),
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def aclose(self) -> None:
        await self._client.aclose()
