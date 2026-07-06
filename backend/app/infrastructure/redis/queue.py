"""ARQ-backed task queue adapter."""
import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.domain.ports.task_queue import TaskQueue

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


class ArqTaskQueue(TaskQueue):
    async def enqueue_agent_task(self, task_id: uuid.UUID) -> None:
        pool = await get_arq_pool()
        await pool.enqueue_job("run_agent_task", str(task_id))

    async def enqueue_workflow_start(self, project_id: uuid.UUID) -> None:
        pool = await get_arq_pool()
        await pool.enqueue_job("start_workflow", str(project_id))

    async def enqueue_embedding(
        self, project_id: uuid.UUID, kind: str, ref_id: uuid.UUID, content: str
    ) -> None:
        pool = await get_arq_pool()
        await pool.enqueue_job("embed_memory", str(project_id), kind, str(ref_id), content)

    async def queue_depth(self) -> int:
        pool = await get_arq_pool()
        return int(await pool.zcard("arq:queue"))


_queue: ArqTaskQueue | None = None


def get_task_queue() -> ArqTaskQueue:
    global _queue
    if _queue is None:
        _queue = ArqTaskQueue()
    return _queue
