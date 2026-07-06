"""Health, readiness, and Prometheus metrics endpoints."""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.infrastructure.db.engine import get_session_factory
from app.infrastructure.redis.client import get_redis

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict[str, str]:
    checks = {"database": "ok", "redis": "ok"}
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"
    try:
        await get_redis().ping()
    except Exception:
        checks["redis"] = "unavailable"
    if any(v != "ok" for v in checks.values()):
        response.status_code = 503
        return {"status": "degraded", **checks}
    return {"status": "ok", **checks}


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
