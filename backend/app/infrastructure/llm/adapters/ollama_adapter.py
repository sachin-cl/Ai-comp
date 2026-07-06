"""Ollama local model adapter (httpx)."""
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.domain.ports.llm_gateway import ChatMessage, LLMResult
from app.domain.value_objects import TokenUsage
from app.infrastructure.llm.base import ProviderAdapter, register_provider


@register_provider("ollama")
class OllamaAdapter(ProviderAdapter):
    name = "ollama"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=get_settings().ollama_base_url)

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
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        start = time.perf_counter()
        resp = await self._client.post("/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return LLMResult(
            text=data.get("message", {}).get("content", ""),
            usage=TokenUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
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
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        start = time.perf_counter()
        usage = TokenUsage()
        full: list[str] = []
        async with self._client.stream("POST", "/api/chat", json=body, timeout=timeout) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    full.append(delta)
                    yield delta
                if chunk.get("done"):
                    usage = TokenUsage(
                        prompt_tokens=chunk.get("prompt_eval_count", 0),
                        completion_tokens=chunk.get("eval_count", 0),
                    )
        yield LLMResult(
            text="".join(full),
            usage=usage,
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def embed(self, texts: list[str], *, model: str, timeout: float) -> list[list[float]]:
        resp = await self._client.post(
            "/api/embed", json={"model": model, "input": texts}, timeout=timeout
        )
        resp.raise_for_status()
        return resp.json().get("embeddings", [])

    async def aclose(self) -> None:
        await self._client.aclose()
