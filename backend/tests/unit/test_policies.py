"""Domain safety policies — the guarantees that keep workflows bounded."""
from datetime import UTC, datetime, timedelta

from app.domain.policies import (
    BudgetPolicy,
    RevisionLoopPolicy,
    SafetyLimits,
    TaskRetryPolicy,
    WorkflowTimeoutPolicy,
)
from app.domain.value_objects import Budget


class TestBudgetPolicy:
    def test_can_spend_under_budget(self):
        assert BudgetPolicy.can_spend(Budget(limit=1000, used=500))

    def test_cannot_spend_at_limit(self):
        assert not BudgetPolicy.can_spend(Budget(limit=1000, used=1000))

    def test_estimated_tokens_counted(self):
        budget = Budget(limit=1000, used=900)
        assert BudgetPolicy.can_spend(budget, estimated_tokens=99)
        assert not BudgetPolicy.can_spend(budget, estimated_tokens=100)


class TestRevisionLoopPolicy:
    def test_allows_up_to_max(self):
        policy = RevisionLoopPolicy(max_loops=3)
        assert policy.can_request_revision(0)
        assert policy.can_request_revision(2)
        assert not policy.can_request_revision(3)
        assert not policy.can_request_revision(4)


class TestTaskRetryPolicy:
    def test_retries_bounded(self):
        policy = TaskRetryPolicy(max_retries=2)
        assert policy.can_retry(1)
        assert policy.can_retry(2)
        assert not policy.can_retry(3)


class TestWorkflowTimeoutPolicy:
    def test_deadline(self):
        start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert WorkflowTimeoutPolicy.deadline(start, 60) == start + timedelta(hours=1)

    def test_expired(self):
        past = datetime.now(UTC) - timedelta(minutes=1)
        future = datetime.now(UTC) + timedelta(minutes=1)
        assert WorkflowTimeoutPolicy.expired(past)
        assert not WorkflowTimeoutPolicy.expired(future)

    def test_none_deadline_never_expires(self):
        assert not WorkflowTimeoutPolicy.expired(None)

    def test_naive_deadline_treated_as_utc(self):
        naive_past = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
        assert WorkflowTimeoutPolicy.expired(naive_past)


def test_safety_limits_defaults():
    limits = SafetyLimits()
    assert limits.max_revision_loops == 3
    assert limits.max_task_retries == 2
    assert limits.token_budget == 2_000_000
