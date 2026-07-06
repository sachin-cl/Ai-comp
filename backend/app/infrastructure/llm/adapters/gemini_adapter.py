"""Google Gemini generateContent adapter (httpx)."""
import json
import time
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.errors import LLMError
from app.domain.ports.llm_gateway import ChatMessage, LLMResult
from app.domain.value_objects import TokenUsage
from app.infrastructure.llm.base import ProviderAdapter, register_provider

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _to_gemini(messages: list[ChatMessage]) -> tuple[dict | None, list[dict]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    system = {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
    contents = [
        {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
        for m in messages
        if m.role != "system"
    ]
    if not contents:
        contents = [{"role": "user", "parts": [{"text": "Proceed."}]}]
    return system, contents


def _usage(data: dict) -> TokenUsage:
    meta = data.get("usageMetadata", {})
    return TokenUsage(
        prompt_tokens=meta.get("promptTokenCount", 0),
        completion_tokens=meta.get("candidatesTokenCount", 0),
    )


@register_provider("gemini")
class GeminiAdapter(ProviderAdapter):
    name = "gemini"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=BASE_URL)

    def _key(self) -> str:
        key = get_settings().gemini_api_key
        if not key:
            raise LLMError("GEMINI_API_KEY is not configured")
        return key

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
        system, contents = _to_gemini(messages)
        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = system
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        start = time.perf_counter()
        resp = await self._client.post(
            f"/models/{model}:generateContent",
            params={"key": self._key()},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        text = ""
        if candidates:
            text = "".join(
                p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])
            )
        return LLMResult(
            text=text,
            usage=_usage(data),
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
        system, contents = _to_gemini(messages)
        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = system
        start = time.perf_counter()
        usage = TokenUsage()
        full: list[str] = []
        async with self._client.stream(
            "POST",
            f"/models/{model}:streamGenerateContent",
            params={"key": self._key(), "alt": "sse"},
            json=body,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                usage = _usage(data) if data.get("usageMetadata") else usage
                for candidate in data.get("candidates") or []:
                    for part in candidate.get("content", {}).get("parts", []):
                        delta = part.get("text", "")
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

    async def aclose(self) -> None:
        await self._client.aclose()
