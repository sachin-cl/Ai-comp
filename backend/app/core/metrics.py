"""Prometheus metrics shared across API and worker."""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "path", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)
QUEUE_DEPTH = Gauge("task_queue_depth", "Tasks currently queued or running")
LLM_TOKENS = Counter(
    "llm_tokens_total", "LLM tokens used", ["provider", "model", "agent", "kind"]
)
LLM_COST = Counter("llm_cost_usd_total", "LLM cost in USD", ["provider", "model", "agent"])
LLM_CALLS = Counter("llm_calls_total", "LLM calls", ["provider", "model", "status"])
AGENT_TASK_DURATION = Histogram(
    "agent_task_duration_seconds",
    "Agent task durations",
    ["agent"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)
WS_CONNECTIONS = Gauge("websocket_connections", "Open WebSocket connections")
