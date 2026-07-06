"""Domain policies: the hard limits that keep workflows bounded."""
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.value_objects import Budget


@dataclass(frozen=True)
class SafetyLimits:
    token_budget: int = 2_000_000
    max_revision_loops: int = 3
    max_task_retries: int = 2
    max_agent_iterations: int = 10
    workflow_timeout_minutes: int = 60


class BudgetPolicy:
    """Checked before every LLM call; never allows an over-budget call to start."""

    @staticmethod
    def can_spend(budget: Budget, estimated_tokens: int = 0) -> bool:
        return budget.used + estimated_tokens < budget.limit


class RevisionLoopPolicy:
    """Bounds review→revision cycles between any reviewer/author pair."""

    def __init__(self, max_loops: int = 3) -> None:
        self.max_loops = max_loops

    def can_request_revision(self, current_round: int) -> bool:
        return current_round < self.max_loops


class WorkflowTimeoutPolicy:
    @staticmethod
    def deadline(started_at: datetime, timeout_minutes: int) -> datetime:
        from datetime import timedelta

        return started_at + timedelta(minutes=timeout_minutes)

    @staticmethod
    def expired(deadline_at: datetime | None) -> bool:
        if deadline_at is None:
            return False
        now = datetime.now(UTC)
        if deadline_at.tzinfo is None:
            deadline_at = deadline_at.replace(tzinfo=UTC)
        return now > deadline_at


class TaskRetryPolicy:
    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries

    def can_retry(self, attempt: int) -> bool:
        """attempt = number of failed attempts so far."""
        return attempt <= self.max_retries
