"""Domain value objects: Budget, TokenUsage, Verdict."""
from app.domain.value_objects import (
    Budget,
    ReviewReason,
    TokenUsage,
    Verdict,
    VerdictType,
)


class TestBudget:
    def test_remaining(self):
        assert Budget(limit=100, used=30).remaining == 70

    def test_remaining_never_negative(self):
        assert Budget(limit=100, used=150).remaining == 0

    def test_exceeded(self):
        assert not Budget(limit=100, used=99).exceeded
        assert Budget(limit=100, used=100).exceeded
        assert Budget(limit=100, used=101).exceeded


class TestTokenUsage:
    def test_total(self):
        assert TokenUsage(prompt_tokens=10, completion_tokens=5).total == 15

    def test_add(self):
        combined = TokenUsage(10, 5) + TokenUsage(1, 2)
        assert combined.prompt_tokens == 11
        assert combined.completion_tokens == 7
        assert combined.total == 18

    def test_default_is_zero(self):
        assert TokenUsage().total == 0


class TestVerdict:
    def test_approved(self):
        assert Verdict(verdict=VerdictType.APPROVED, summary="ok").approved

    def test_changes_requested_not_approved(self):
        verdict = Verdict(
            verdict=VerdictType.CHANGES_REQUESTED,
            summary="fix",
            reasons=(
                ReviewReason(
                    severity="high",
                    area="api",
                    target_node="backend_impl",
                    description="missing endpoint",
                ),
            ),
        )
        assert not verdict.approved
        assert verdict.reasons[0].suggestion == ""
