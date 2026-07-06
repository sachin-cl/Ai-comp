"""DefaultLLMGateway: retries with backoff+jitter, budget enforcement, circuit breaker,
token/cost accounting, Prometheus metrics, and the llm_calls ledger."""
import asyncio
import random
import uuid
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.errors import BudgetExceededError, LLMError, LLMTimeoutError
from app.core.logging import get_logger
from app.core.metrics import LLM_CALLS, LLM_COST, LLM_TOKENS
from app.domain.entities import LLMCallRecord
from app.domain.policies import BudgetPolicy
from app.domain.ports.llm_gateway import ChatMessage, LLMCallContext, LLMGateway, LLMResult
from app.domain.value_objects import Budget
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import SqlLLMCallRepository, SqlProjectRepository
from app.infrastructure.llm import adapters  # noqa: F401  (self-registration)
from app.infrastructure.llm.base import ProviderAdapter, get_provider_class
from app.infrastructure.llm.circuit_breaker import CircuitBreaker
from app.infrastructure.llm.pricing import compute_cost

logger = get_logger("llm.gateway")

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class DefaultLLMGateway(LLMGateway):
    def __init__(self) -> None:
        settings = get_settings()
        self._adapters: dict[str, ProviderAdapter] = {}
        self._breaker = CircuitBreaker(
            threshold=settings.circuit_breaker_threshold,
            reset_seconds=settings.circuit_breaker_reset_seconds,
        )
        self._max_retries = settings.llm_max_retries
        self._timeout = settings.llm_timeout_seconds

    def _adapter(self, provider: str) -> ProviderAdapter:
        if provider not in self._adapters:
            self._adapters[provider] = get_provider_class(provider)()
        return self._adapters[provider]

    async def _check_budget(self, context: LLMCallContext) -> None:
        if context.project_id is None:
            return
        async with session_scope() as session:
            project = await SqlProjectRepository(session).get(context.project_id)
        if project is None:
            return
        budget = Budget(limit=project.token_budget, used=project.tokens_used)
        if not BudgetPolicy.can_spend(budget):
            raise BudgetExceededError(
                f"Project token budget exhausted ({budget.used}/{budget.limit})",
                details={"tokens_used": budget.used, "token_budget": budget.limit},
            )

    async def _record(
        self,
        context: LLMCallContext,
        *,
        provider: str,
        model: str,
        result: LLMResult | None,
        status: str,
        error: str | None = None,
        latency_ms: int = 0,
    ) -> None:
        prompt_tokens = result.usage.prompt_tokens if result else 0
        completion_tokens = result.usage.completion_tokens if result else 0
        cost = compute_cost(model, prompt_tokens, completion_tokens)
        LLM_CALLS.labels(provider, model, status).inc()
        if result:
            agent = context.agent_key or "unknown"
            LLM_TOKENS.labels(provider, model, agent, "prompt").inc(prompt_tokens)
            LLM_TOKENS.labels(provider, model, agent, "completion").inc(completion_tokens)
            LLM_COST.labels(provider, model, agent).inc(cost)
        try:
            async with session_scope() as session:
                await SqlLLMCallRepository(session).add(
                    LLMCallRecord(
                        id=uuid.uuid4(),
                        provider=provider,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost,
                        latency_ms=result.latency_ms if result else latency_ms,
                        status=status,
                        project_id=context.project_id,
                        task_id=context.task_id,
                        agent_id=context.agent_id,
                        correlation_id=context.correlation_id,
                        error=error,
                    )
                )
                if context.project_id and result:
                    await SqlProjectRepository(session).add_usage(
                        context.project_id, result.usage.total, cost
                    )
        except Exception:
            logger.warning("llm_ledger_write_failed", exc_info=True)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        provider: str,
        model: str,
        context: LLMCallContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResult:
        await self._check_budget(context)
        adapter = self._adapter(provider)
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            self._breaker.check(provider)
            try:
                result = await adapter.complete(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self._timeout,
                    json_mode=json_mode,
                )
                self._breaker.record_success(provider)
                await self._record(
                    context, provider=provider, model=model, result=result, status="ok"
                )
                return result
            except httpx.TimeoutException:
                last_error = LLMTimeoutError(f"{provider} call timed out after {self._timeout}s")
                retryable = True
                self._breaker.record_failure(provider)
                logger.warning("llm_timeout", provider=provider, model=model, attempt=attempt)
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code in RETRYABLE_STATUS
                last_error = LLMError(
                    f"{provider} returned {exc.response.status_code}",
                    details={"status": exc.response.status_code},
                )
                self._breaker.record_failure(provider)
                logger.warning(
                    "llm_http_error",
                    provider=provider,
                    status=exc.response.status_code,
                    attempt=attempt,
                )
            except httpx.HTTPError as exc:
                retryable = True
                last_error = LLMError(f"{provider} connection error: {exc}")
                self._breaker.record_failure(provider)
                logger.warning("llm_connection_error", provider=provider, attempt=attempt)

            if not retryable or attempt == self._max_retries - 1:
                break
            # Exponential backoff with full jitter: sleep in [0, base * 2^attempt]
            await asyncio.sleep(random.uniform(0, 1.0 * (2**attempt)))

        error = last_error or LLMError(f"{provider} call failed")
        await self._record(
            context,
            provider=provider,
            model=model,
            result=None,
            status="timeout" if isinstance(error, LLMTimeoutError) else "error",
            error=str(error),
        )
        raise error

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        provider: str,
        model: str,
        context: LLMCallContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        await self._check_budget(context)
        self._breaker.check(provider)
        adapter = self._adapter(provider)
        try:
            async for item in adapter.stream(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self._timeout,
            ):
                if isinstance(item, LLMResult):
                    self._breaker.record_success(provider)
                    await self._record(
                        context, provider=provider, model=model, result=item, status="ok"
                    )
                else:
                    yield item
        except httpx.HTTPError as exc:
            self._breaker.record_failure(provider)
            await self._record(
                context, provider=provider, model=model, result=None,
                status="error", error=str(exc),
            )
            raise LLMError(f"{provider} stream failed: {exc}") from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        settings = get_settings()
        if settings.embedding_provider == "openai" and settings.openai_api_key:
            adapter = self._adapter("openai")
            return await adapter.embed(
                texts, model="text-embedding-3-small", timeout=self._timeout
            )
        from app.infrastructure.memory.embedder import hash_embedding

        return [hash_embedding(t) for t in texts]

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            await adapter.aclose()


_gateway: DefaultLLMGateway | None = None


def get_llm_gateway() -> DefaultLLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = DefaultLLMGateway()
    return _gateway
