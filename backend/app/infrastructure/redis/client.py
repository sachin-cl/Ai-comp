"""Shared async Redis client (or its in-process stand-in for standalone mode)."""
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_redis: Any | None = None


def get_redis() -> Any:
    """Real Redis normally; MemoryRedis when REDIS_URL=memory:// (standalone dev)."""
    global _redis
    if _redis is None:
        url = get_settings().redis_url
        if url.startswith("memory://"):
            from app.infrastructure.redis.memory_backend import MemoryRedis

            _redis = MemoryRedis()
        else:
            _redis = aioredis.from_url(url, decode_responses=True, health_check_interval=30)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None
