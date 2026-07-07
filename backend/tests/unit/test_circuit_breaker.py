"""Circuit breaker: open after threshold, half-open probe after reset window."""
import pytest

import app.infrastructure.llm.circuit_breaker as cb_mod
from app.core.errors import CircuitOpenError
from app.infrastructure.llm.circuit_breaker import CircuitBreaker


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(cb_mod.time, "monotonic", fake)
    return fake


def test_closed_circuit_allows_calls(clock):
    breaker = CircuitBreaker(threshold=3)
    breaker.check("openai")  # no raise


def test_opens_after_threshold_failures(clock):
    breaker = CircuitBreaker(threshold=3)
    for _ in range(3):
        breaker.record_failure("openai")
    with pytest.raises(CircuitOpenError):
        breaker.check("openai")


def test_failures_below_threshold_stay_closed(clock):
    breaker = CircuitBreaker(threshold=3)
    breaker.record_failure("openai")
    breaker.record_failure("openai")
    breaker.check("openai")  # still closed


def test_success_resets_failure_count(clock):
    breaker = CircuitBreaker(threshold=3)
    breaker.record_failure("openai")
    breaker.record_failure("openai")
    breaker.record_success("openai")
    for _ in range(2):
        breaker.record_failure("openai")
    breaker.check("openai")  # 2 < 3, closed


def test_half_open_after_reset_window(clock):
    breaker = CircuitBreaker(threshold=2, reset_seconds=60)
    breaker.record_failure("openai")
    breaker.record_failure("openai")
    with pytest.raises(CircuitOpenError):
        breaker.check("openai")

    clock.now += 61
    breaker.check("openai")  # half-open: one probe allowed

    # A failed probe reopens immediately …
    breaker.record_failure("openai")
    with pytest.raises(CircuitOpenError):
        breaker.check("openai")

    # … a successful probe closes it for good.
    clock.now += 61
    breaker.check("openai")
    breaker.record_success("openai")
    breaker.check("openai")


def test_providers_isolated(clock):
    breaker = CircuitBreaker(threshold=1)
    breaker.record_failure("openai")
    with pytest.raises(CircuitOpenError):
        breaker.check("openai")
    breaker.check("anthropic")  # unaffected
