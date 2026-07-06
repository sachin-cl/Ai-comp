"""Three-tier memory service (see docs/agent-internals.md §2).

Tier 1 (working) is assembled by the prompt builder from what this service returns.
Tier 2 (project) = project_memories rows. Tier 3 (semantic) = pgvector embeddings.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.entities import ProjectMemory
from app.domain.ports.llm_gateway import LLMGateway
from app.domain.ports.memory_store import MemoryHit
from app.domain.value_objects import MemoryCategory
from app.infrastructure.db.repositories import SqlProjectMemoryRepository
from app.infrastructure.memory.vector_store import PgVectorStore

logger = get_logger("memory")

MAX_PROJECT_MEMORIES = 60
CONSOLIDATE_BATCH = 20


class MemoryService:
    def __init__(self, session: AsyncSession, gateway: LLMGateway) -> None:
        self.session = session
        self.repo = SqlProjectMemoryRepository(session)
        self.vector_store = PgVectorStore(session)
        self.gateway = gateway

    async def record_decisions(
        self,
        project_id: uuid.UUID,
        decisions: list[str],
        source_task_id: uuid.UUID | None = None,
        category: MemoryCategory = MemoryCategory.DECISION,
    ) -> None:
        for decision in decisions[:5]:
            if not decision.strip():
                continue
            await self.repo.add(
                ProjectMemory(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    category=category,
                    content=decision.strip()[:500],
                    source_task_id=source_task_id,
                )
            )
        await self._maybe_consolidate(project_id)

    async def _maybe_consolidate(self, project_id: uuid.UUID) -> None:
        """Keep tier-2 bounded: extractively merge the oldest rows into one summary."""
        count = await self.repo.count_for_project(project_id)
        if count <= MAX_PROJECT_MEMORIES:
            return
        oldest = await self.repo.list_for_project(project_id, limit=CONSOLIDATE_BATCH)
        merged = "; ".join(m.content for m in oldest)[:1_500]
        await self.repo.delete_many([m.id for m in oldest])
        await self.repo.add(
            ProjectMemory(
                id=uuid.uuid4(),
                project_id=project_id,
                category=MemoryCategory.SUMMARY,
                content=f"Consolidated earlier decisions: {merged}",
            )
        )
        logger.info("memories_consolidated", project_id=str(project_id), merged=len(oldest))

    async def project_context(self, project_id: uuid.UUID) -> list[ProjectMemory]:
        return await self.repo.list_for_project(project_id, limit=40)

    async def semantic_recall(
        self, project_id: uuid.UUID, query_text: str, limit: int = 5
    ) -> list[MemoryHit]:
        try:
            [embedding] = await self.gateway.embed([query_text[:2_000]])
            return await self.vector_store.search(
                embedding, limit=limit, min_similarity=0.75, project_id=project_id
            )
        except Exception:
            logger.warning("semantic_recall_failed", exc_info=True)
            return []

    async def embed_and_store(
        self, project_id: uuid.UUID, kind: str, ref_id: uuid.UUID, content: str
    ) -> None:
        chunks = [content[i : i + 1_000] for i in range(0, min(len(content), 4_000), 1_000)]
        embeddings = await self.gateway.embed(chunks)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            await self.vector_store.add(
                content=chunk,
                embedding=embedding,
                kind=kind,
                ref_id=ref_id,
                project_id=project_id,
            )
