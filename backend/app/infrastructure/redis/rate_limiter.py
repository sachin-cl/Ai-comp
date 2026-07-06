"""Redis sliding-window rate limiter."""
import time

from app.core.errors import RateLimitedError
from app.infrastructure.redis.client import get_redis


async def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Raise RateLimitedError if `key` exceeded `limit` events in the window."""
    redis = get_redis()
    now = time.time()
    bucket = f"ratelimit:{key}"
    pipe = redis.pipeline()
    pipe.zremrangebyscore(bucket, 0, now - window_seconds)
    pipe.zadd(bucket, {f"{now}": now})
    pipe.zcard(bucket)
    pipe.expire(bucket, window_seconds + 1)
    _, _, count, _ = await pipe.execute()
    if int(count) > limit:
        raise RateLimitedError(
            "Too many requests, slow down",
            details={"limit": limit, "window_seconds": window_seconds},
        )
