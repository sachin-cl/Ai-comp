"""Typed exception hierarchy mapped to a consistent error envelope."""
from typing import Any


class AppError(Exception):
    """Base application error. Subclasses set code + HTTP status."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str = "", details: dict[str, Any] | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.code.replace("_", " ").title()
        self.details = details or {}

    def envelope(self, correlation_id: str = "") -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "correlation_id": correlation_id,
            }
        }


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = 401


class InvalidCredentialsError(UnauthorizedError):
    code = "INVALID_CREDENTIALS"


class InvalidRefreshTokenError(UnauthorizedError):
    code = "INVALID_REFRESH_TOKEN"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class EmailTakenError(ConflictError):
    code = "EMAIL_TAKEN"


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    status_code = 429


class BudgetExceededError(AppError):
    code = "BUDGET_EXCEEDED"
    status_code = 409


class RevisionLoopExceededError(AppError):
    code = "REVISION_LOOP_EXCEEDED"
    status_code = 409


class WorkflowTimeoutError(AppError):
    code = "WORKFLOW_TIMEOUT"
    status_code = 409


class LLMError(AppError):
    code = "LLM_ERROR"
    status_code = 502


class LLMTimeoutError(LLMError):
    code = "LLM_TIMEOUT"


class CircuitOpenError(LLMError):
    code = "LLM_CIRCUIT_OPEN"


class MalformedOutputError(LLMError):
    code = "LLM_MALFORMED_OUTPUT"
