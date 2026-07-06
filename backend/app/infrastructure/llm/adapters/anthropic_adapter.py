"""Anthropic Messages API adapter (httpx)."""
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.errors import LLMError
from app.domain.ports.llm_gateway import ChatMessage, LLMResult
from app.domain.value_objects import TokenUsage
from app.infrastructure.llm.base import ProviderAdapter, register_provider

BASE_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


def _split_system(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    rest = [
        {"role": m.role, "content": m.content} for m in messages if m.role != "system"
    ]
    if not rest:
        rest = [{"role": "user", "content": "Proceed."}]
    return system, rest


@register_provider("anthropic")
class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE_URL)

    def _headers(self) -> dict[str, str]:
        key = get_settings().anthropic_api_key
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not configured")
        return {"x-api-key": key, "anthropic-version": API_VERSION}

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
        system, rest = _split_system(messages)
        if json_mode:
            system += "\n\nRespond with a single valid JSON object and nothing else."
        body = {
            "model": model,
            "system": system,
            "messages": rest,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        start = time.perf_counter()
        resp = await self._client.post(
            "/messages", json=body, headers=self._headers(), timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        return LLMResult(
            text=text,
            usage=TokenUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
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
        system, rest = _split_system(messages)
        body = {
            "model": model,
            "system": system,
            "messages": rest,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        start = time.perf_counter()
        prompt_tokens = completion_tokens = 0
        full: list[str] = []
        async with self._client.stream(
            "POST", "/messages", json=body, headers=self._headers(), timeout=timeout
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                etype = event.get("type")
                if etype == "message_start":
                    prompt_tokens = event["message"].get("usage", {}).get("input_tokens", 0)
                elif etype == "content_block_delta":
                    delta = event.get("delta", {}).get("text", "")
                    if delta:
                        full.append(delta)
                        yield delta
                elif etype == "message_delta":
                    completion_tokens = event.get("usage", {}).get("output_tokens", 0)
        yield LLMResult(
            text="".join(full),
            usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
            model=model,
            provider=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
