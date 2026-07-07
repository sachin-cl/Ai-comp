"""In-process substitutes for Redis and ARQ, enabling standalone dev mode.

Activated with REDIS_URL=memory:// (paired with a SQLite DATABASE_URL this runs
the whole platform in a single process — no Docker, no external services).

MemoryRedis implements only the slice of the redis-py asyncio API this codebase
uses: publish/pubsub (event fan-out to WebSockets), pipeline with sorted-set ops
(the sliding-window rate limiter), and ping (readiness). InlineTaskQueue replaces
the ARQ worker by running jobs as asyncio background tasks in the API process.

Single-process only by design: multi-replica deployments need real Redis.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.logging import get_logger
from app.domain.ports.task_queue import TaskQueue

logger = get_logger("memory_backend")

_CLOSED = object()


class MemoryPubSub:
    def __init__(self, broker: "MemoryRedis") -> None:
        self._broker = broker
        self.channels: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        broker._pubsubs.add(self)

    async def subscribe(self, *channels: str) -> None:
        self.channels.update(channels)

    async def unsubscribe(self, *channels: str) -> None:
        if channels:
            self.channels.difference_update(channels)
        else:
            self.channels.clear()

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self.queue.get()
            if item is _CLOSED:
                return
            yield item

    async def aclose(self) -> None:
        self._broker._pubsubs.discard(self)
        self.queue.put_nowait(_CLOSED)


class MemoryPipeline:
    """Queued sorted-set ops matching the rate limiter's usage."""

    def __init__(self, broker: "MemoryRedis") -> None:
        self._broker = broker
        self._ops: list[tuple] = []

    def zremrangebyscore(self, key: str, low: float, high: float) -> "MemoryPipeline":
        self._ops.append(("zremrangebyscore", key, low, high))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> "MemoryPipeline":
        self._ops.append(("zadd", key, mapping))
        return self

    def zcard(self, key: str) -> "MemoryPipeline":
        self._ops.append(("zcard", key))
        return self

    def expire(self, key: str, seconds: int) -> "MemoryPipeline":
        self._ops.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        zsets = self._broker._zsets
        for op, key, *args in self._ops:
            bucket = zsets.setdefault(key, {})
            if op == "zremrangebyscore":
                low, high = args
                doomed = [m for m, s in bucket.items() if low <= s <= high]
                for member in doomed:
                    del bucket[member]
                results.append(len(doomed))
            elif op == "zadd":
                (mapping,) = args
                added = sum(1 for m in mapping if m not in bucket)
                bucket.update(mapping)
                results.append(added)
            elif op == "zcard":
                results.append(len(bucket))
            elif op == "expire":
                results.append(True)  # buckets are pruned by zremrangebyscore each call
        self._ops.clear()
        return results


class MemoryRedis:
    """Single-process broker mimicking the redis-py surface this app touches."""

    def __init__(self) -> None:
        self._pubsubs: set[MemoryPubSub] = set()
        self._zsets: dict[str, dict[str, float]] = {}

    async def publish(self, channel: str, data: str) -> int:
        delivered = 0
        for pubsub in list(self._pubsubs):
            if channel in pubsub.channels:
                pubsub.queue.put_nowait(
                    {"type": "message", "channel": channel, "data": data}
                )
                delivered += 1
        return delivered

    def pubsub(self) -> MemoryPubSub:
        return MemoryPubSub(self)

    def pipeline(self) -> MemoryPipeline:
        return MemoryPipeline(self)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        for pubsub in list(self._pubsubs):
            await pubsub.aclose()


class InlineTaskQueue(TaskQueue):
    """Runs orchestrator jobs as asyncio tasks in the API process (no worker)."""

    def __init__(self) -> None:
        self._pending: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._pending.add(task)
        task.add_done_callback(self._finish)

    def _finish(self, task: asyncio.Task) -> None:
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("inline_job_failed", exc_info=task.exception())

    async def enqueue_agent_task(self, task_id: uuid.UUID) -> None:
        from app.application.orchestration.orchestrator import get_orchestrator

        self._spawn(get_orchestrator().run_agent_task(task_id))

    async def enqueue_workflow_start(self, project_id: uuid.UUID) -> None:
        from app.application.orchestration.orchestrator import get_orchestrator

        self._spawn(get_orchestrator().start_workflow(project_id))

    async def enqueue_embedding(
        self, project_id: uuid.UUID, kind: str, ref_id: uuid.UUID, content: str
    ) -> None:
        self._spawn(self._embed(project_id, kind, ref_id, content))

    @staticmethod
    async def _embed(project_id: uuid.UUID, kind: str, ref_id: uuid.UUID,
                     content: str) -> None:
        from app.application.services.memory_service import MemoryService
        from app.infrastructure.db.engine import session_scope
        from app.infrastructure.llm.gateway import get_llm_gateway

        try:
            async with session_scope() as session:
                await MemoryService(session, get_llm_gateway()).embed_and_store(
                    project_id, kind, ref_id, content
                )
        except Exception:
            logger.warning("inline_embed_failed", kind=kind, exc_info=True)

    async def queue_depth(self) -> int:
        return len(self._pending)
