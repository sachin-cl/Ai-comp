"""Vector store port for tier-3 semantic memory."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryHit:
    content: str
    kind: str
    similarity: float
    ref_id: uuid.UUID | None = None


class VectorStore(ABC):
    @abstractmethod
    async def add(
        self,
        *,
        content: str,
        embedding: list[float],
        kind: str,
        ref_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        embedding: list[float],
        *,
        limit: int = 5,
        min_similarity: float = 0.75,
        project_id: uuid.UUID | None = None,
    ) -> list[MemoryHit]: ...
