"""LLM gateway port — the only way any part of the system talks to a model."""
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.domain.value_objects import TokenUsage


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResult:
    text: str
    usage: TokenUsage
    model: str
    provider: str
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMCallContext:
    """Attribution for budgeting, metrics, and the llm_calls ledger."""

    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    agent_key: str = ""
    correlation_id: uuid.UUID | None = None


class LLMGateway(ABC):
    """Provider-agnostic gateway with retries, budgets, and usage tracking built in."""

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        provider: str,
        model: str,
        context: LLMCallContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResult: ...

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        provider: str,
        model: str,
        context: LLMCallContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield text deltas; usage recorded when the stream closes."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
