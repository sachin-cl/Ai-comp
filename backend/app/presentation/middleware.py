"""Request middleware: correlation IDs, logging, metrics, security headers."""
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import correlation_id_var, get_logger, new_correlation_id
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

logger = get_logger("http")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-correlation-id")
        cid = incoming or new_correlation_id()
        correlation_id_var.set(cid)
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        if path_template not in ("/metrics", "/health", "/ready"):
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 2),
                client=request.client.host if request.client else None,
            )
        HTTP_REQUESTS.labels(request.method, path_template, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, path_template).observe(duration)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        return response
