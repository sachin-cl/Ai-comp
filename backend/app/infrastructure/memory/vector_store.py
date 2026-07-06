"""pgvector-backed vector store with a pure-SQL cosine fallback for non-Postgres tests."""
import math
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.memory_store import MemoryHit, VectorStore
from app.infrastructure.db import models as m


class PgVectorStore(VectorStore):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def _is_postgres(self) -> bool:
        return bool(self.session.bind) and self.session.bind.dialect.name == "postgresql"

    async def add(
        self,
        *,
        content: str,
        embedding: list[float],
        kind: str,
        ref_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        row = m.MemoryEmbeddingModel(
            project_id=project_id, kind=kind, ref_id=ref_id, content=content,
            embedding=embedding,
        )
        self.session.add(row)
        await self.session.flush()
        if self._is_postgres:
            await self.session.execute(
                text(
                    "UPDATE memory_embeddings SET embedding_vec = CAST(:emb AS vector) "
                    "WHERE id = :id"
                ),
                {"emb": str(embedding), "id": str(row.id)},
            )

    async def search(
        self,
        embedding: list[float],
        *,
        limit: int = 5,
        min_similarity: float = 0.75,
        project_id: uuid.UUID | None = None,
    ) -> list[MemoryHit]:
        if self._is_postgres:
            where = "embedding_vec IS NOT NULL"
            params: dict = {"emb": str(embedding), "limit": limit, "min_sim": min_similarity}
            if project_id is not None:
                where += " AND (project_id = :pid OR project_id IS NULL)"
                params["pid"] = str(project_id)
            result = await self.session.execute(
                text(
                    f"SELECT content, kind, ref_id, "
                    f"1 - (embedding_vec <=> CAST(:emb AS vector)) AS similarity "
                    f"FROM memory_embeddings WHERE {where} "
                    f"ORDER BY embedding_vec <=> CAST(:emb AS vector) LIMIT :limit"
                ),
                params,
            )
            return [
                MemoryHit(
                    content=r.content,
                    kind=r.kind,
                    ref_id=uuid.UUID(str(r.ref_id)) if r.ref_id else None,
                    similarity=float(r.similarity),
                )
                for r in result.all()
                if float(r.similarity) >= min_similarity
            ]

        # Fallback (SQLite tests): brute-force cosine over the JSON column.
        query = select(m.MemoryEmbeddingModel)
        if project_id is not None:
            query = query.where(
                (m.MemoryEmbeddingModel.project_id == project_id)
                | (m.MemoryEmbeddingModel.project_id.is_(None))
            )
        rows = (await self.session.execute(query)).scalars().all()
        hits = []
        for row in rows:
            if not row.embedding:
                continue
            sim = _cosine(embedding, row.embedding)
            if sim >= min_similarity:
                hits.append(
                    MemoryHit(content=row.content, kind=row.kind, ref_id=row.ref_id,
                              similarity=sim)
                )
        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[:limit]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
