"""Per-provider circuit breaker: fail fast during provider outages."""
import time

from app.core.errors import CircuitOpenError
from app.core.logging import get_logger

logger = get_logger("llm.circuit")


class CircuitBreaker:
    def __init__(self, threshold: int = 5, reset_seconds: float = 60.0) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def check(self, provider: str) -> None:
        """Raise CircuitOpenError if the circuit is open (and not yet half-open)."""
        opened = self._opened_at.get(provider)
        if opened is None:
            return
        if time.monotonic() - opened >= self.reset_seconds:
            # Half-open: allow one probe call through.
            logger.info("circuit_half_open", provider=provider)
            del self._opened_at[provider]
            self._failures[provider] = self.threshold - 1
            return
        raise CircuitOpenError(f"Circuit open for provider '{provider}'")

    def record_success(self, provider: str) -> None:
        self._failures[provider] = 0
        self._opened_at.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        if count >= self.threshold and provider not in self._opened_at:
            self._opened_at[provider] = time.monotonic()
            logger.warning("circuit_opened", provider=provider, failures=count)
