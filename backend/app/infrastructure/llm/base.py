"""Provider adapter interface + registry."""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.ports.llm_gateway import ChatMessage, LLMResult

_PROVIDERS: dict[str, type["ProviderAdapter"]] = {}


def register_provider(name: str):
    def deco(cls: type["ProviderAdapter"]) -> type["ProviderAdapter"]:
        _PROVIDERS[name] = cls
        return cls

    return deco


def get_provider_class(name: str) -> type["ProviderAdapter"]:
    if name not in _PROVIDERS:
        raise KeyError(f"Unknown LLM provider '{name}'. Registered: {sorted(_PROVIDERS)}")
    return _PROVIDERS[name]


class ProviderAdapter(ABC):
    """One instance per provider; stateless besides its HTTP client."""

    name: str = ""

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
        json_mode: bool = False,
    ) -> LLMResult: ...

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> AsyncIterator[LLMResult | str]:
        """Yield str deltas, then a final LLMResult with usage."""
        ...

    async def embed(self, texts: list[str], *, model: str, timeout: float) -> list[list[float]]:
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def aclose(self) -> None:  # pragma: no cover - trivial
        pass
