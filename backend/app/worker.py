"""ARQ worker: executes agent tasks, workflow starts, and embedding jobs.

Run with: arq app.worker.WorkerSettings
"""
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import QUEUE_DEPTH
from app.infrastructure.redis.queue import redis_settings

logger = get_logger("worker")


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=True)
    from app.agents.registry import sync_agents_to_db

    await sync_agents_to_db()
    logger.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.infrastructure.db.engine import dispose_engine
    from app.infrastructure.llm.gateway import get_llm_gateway
    from app.infrastructure.redis.client import close_redis
    from app.infrastructure.redis.queue import close_arq_pool

    await get_llm_gateway().aclose()
    await dispose_engine()
    await close_arq_pool()
    await close_redis()
    logger.info("worker_stopped")


async def start_workflow(ctx: dict[str, Any], project_id: str) -> None:
    from app.application.orchestration.orchestrator import get_orchestrator

    QUEUE_DEPTH.inc()
    try:
        await get_orchestrator().start_workflow(uuid.UUID(project_id))
    finally:
        QUEUE_DEPTH.dec()


async def run_agent_task(ctx: dict[str, Any], task_id: str) -> None:
    from app.application.orchestration.orchestrator import get_orchestrator

    QUEUE_DEPTH.inc()
    try:
        await get_orchestrator().run_agent_task(uuid.UUID(task_id))
    finally:
        QUEUE_DEPTH.dec()


async def embed_memory(
    ctx: dict[str, Any], project_id: str, kind: str, ref_id: str, content: str
) -> None:
    from app.application.services.memory_service import MemoryService
    from app.infrastructure.db.engine import session_scope
    from app.infrastructure.llm.gateway import get_llm_gateway

    try:
        async with session_scope() as session:
            await MemoryService(session, get_llm_gateway()).embed_and_store(
                uuid.UUID(project_id), kind, uuid.UUID(ref_id), content
            )
    except Exception:
        logger.warning("embed_memory_failed", kind=kind, exc_info=True)


class WorkerSettings:
    functions = [start_workflow, run_agent_task, embed_memory]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 10
    job_timeout = 600
    max_tries = 3  # 1 initial + 2 task-level retries (ARQ re-delivery on crash)
    health_check_interval = 30
