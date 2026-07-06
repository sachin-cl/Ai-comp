"""Enums and immutable value objects shared across the domain."""
from dataclasses import dataclass, field
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class ProjectStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    NEEDS_ATTENTION = "needs_attention"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# A workflow's lifecycle mirrors its project's.
WorkflowStatus = ProjectStatus


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    REVISION = "revision"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class MessageType(StrEnum):
    ASSIGNMENT = "assignment"
    RESULT = "result"
    REVIEW = "review"
    REVISION_REQUEST = "revision_request"
    STATUS = "status"
    SYSTEM = "system"


class VerdictType(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    MOCK = "mock"


class MemoryCategory(StrEnum):
    DECISION = "decision"
    REQUIREMENT = "requirement"
    CONSTRAINT = "constraint"
    SUMMARY = "summary"


class NotificationType(StrEnum):
    WORKFLOW_COMPLETED = "workflow_completed"
    NEEDS_ATTENTION = "needs_attention"
    APPROVAL_REQUIRED = "approval_required"
    TASK_FAILED = "task_failed"
    PROJECT_CANCELLED = "project_cancelled"


@dataclass(frozen=True)
class Budget:
    """Token budget for a project."""

    limit: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def exceeded(self) -> bool:
        return self.used >= self.limit


@dataclass(frozen=True)
class ReviewReason:
    severity: str  # "high" | "medium" | "low"
    area: str
    target_node: str
    description: str
    suggestion: str = ""


@dataclass(frozen=True)
class Verdict:
    verdict: VerdictType
    summary: str
    reasons: tuple[ReviewReason, ...] = field(default_factory=tuple)

    @property
    def approved(self) -> bool:
        return self.verdict == VerdictType.APPROVED


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True)
class GeneratedFile:
    """A file emitted by an agent, before it becomes a stored artifact."""

    path: str
    content: str
    language: str = "text"
