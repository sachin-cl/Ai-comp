"""Repository ports. One protocol per aggregate; implementations live in infrastructure."""
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.domain.entities import (
    AgentMessage,
    AgentProfile,
    Artifact,
    ArtifactVersion,
    LLMCallRecord,
    Notification,
    Project,
    ProjectMemory,
    Review,
    Task,
    User,
    Workflow,
)
from app.domain.value_objects import (
    MemoryCategory,
    ProjectStatus,
    TaskStatus,
    WorkflowStatus,
)


class UserRepository(ABC):
    @abstractmethod
    async def add(self, user: User) -> User: ...
    @abstractmethod
    async def get(self, user_id: uuid.UUID) -> User | None: ...
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...
    @abstractmethod
    async def save_refresh_token(
        self, user_id: uuid.UUID, token_hash: str, expires_at: Any
    ) -> None: ...
    @abstractmethod
    async def get_refresh_token_user(self, token_hash: str) -> User | None: ...
    @abstractmethod
    async def revoke_refresh_token(self, token_hash: str) -> None: ...


class AgentRepository(ABC):
    @abstractmethod
    async def upsert(self, profile: AgentProfile) -> AgentProfile: ...
    @abstractmethod
    async def get_by_key(self, key: str) -> AgentProfile | None: ...
    @abstractmethod
    async def list_active(self) -> list[AgentProfile]: ...


class ProjectRepository(ABC):
    @abstractmethod
    async def add(self, project: Project) -> Project: ...
    @abstractmethod
    async def get(self, project_id: uuid.UUID) -> Project | None: ...
    @abstractmethod
    async def list_for_owner(
        self, owner_id: uuid.UUID | None, limit: int, offset: int
    ) -> tuple[list[Project], int]: ...
    @abstractmethod
    async def update_status(self, project_id: uuid.UUID, status: ProjectStatus) -> None: ...
    @abstractmethod
    async def update_fields(self, project_id: uuid.UUID, **fields: Any) -> None: ...
    @abstractmethod
    async def add_usage(
        self, project_id: uuid.UUID, tokens: int, cost_usd: float
    ) -> tuple[int, float]:
        """Atomically add usage; returns new (tokens_used, cost_usd)."""
        ...


class WorkflowRepository(ABC):
    @abstractmethod
    async def add(self, workflow: Workflow) -> Workflow: ...
    @abstractmethod
    async def get(self, workflow_id: uuid.UUID) -> Workflow | None: ...
    @abstractmethod
    async def get_by_project(self, project_id: uuid.UUID) -> Workflow | None: ...
    @abstractmethod
    async def update_fields(self, workflow_id: uuid.UUID, **fields: Any) -> None: ...
    @abstractmethod
    async def set_status(
        self, workflow_id: uuid.UUID, status: WorkflowStatus, paused_reason: str | None = None
    ) -> None: ...


class TaskRepository(ABC):
    @abstractmethod
    async def add(self, task: Task) -> Task: ...
    @abstractmethod
    async def get(self, task_id: uuid.UUID) -> Task | None: ...
    @abstractmethod
    async def list_for_project(
        self, project_id: uuid.UUID, status: TaskStatus | None = None
    ) -> list[Task]: ...
    @abstractmethod
    async def list_for_workflow(self, workflow_id: uuid.UUID) -> list[Task]: ...
    @abstractmethod
    async def update_fields(self, task_id: uuid.UUID, **fields: Any) -> None: ...
    @abstractmethod
    async def try_mark_running(self, task_id: uuid.UUID) -> bool:
        """Atomic queued→running transition; False if already claimed (idempotency guard)."""
        ...
    @abstractmethod
    async def add_dependency(self, task_id: uuid.UUID, depends_on: uuid.UUID) -> None: ...


class MessageRepository(ABC):
    @abstractmethod
    async def add(self, message: AgentMessage) -> AgentMessage:
        """Persist and assign the per-project monotonic seq."""
        ...
    @abstractmethod
    async def list_for_project(
        self, project_id: uuid.UUID, limit: int, offset: int, after_seq: int | None = None
    ) -> tuple[list[AgentMessage], int]: ...
    @abstractmethod
    async def list_for_task(self, task_id: uuid.UUID) -> list[AgentMessage]: ...


class ArtifactRepository(ABC):
    @abstractmethod
    async def get_by_path(self, project_id: uuid.UUID, path: str) -> Artifact | None: ...
    @abstractmethod
    async def get(self, artifact_id: uuid.UUID) -> Artifact | None: ...
    @abstractmethod
    async def add(self, artifact: Artifact) -> Artifact: ...
    @abstractmethod
    async def list_for_project(self, project_id: uuid.UUID) -> list[Artifact]: ...
    @abstractmethod
    async def add_version(self, version: ArtifactVersion) -> ArtifactVersion: ...
    @abstractmethod
    async def get_version(self, artifact_id: uuid.UUID, version: int) -> ArtifactVersion | None: ...
    @abstractmethod
    async def list_versions(self, artifact_id: uuid.UUID) -> list[ArtifactVersion]: ...
    @abstractmethod
    async def latest_versions_for_project(
        self, project_id: uuid.UUID
    ) -> list[tuple[Artifact, ArtifactVersion]]: ...
    @abstractmethod
    async def bump_latest(self, artifact_id: uuid.UUID, version: int) -> None: ...


class ReviewRepository(ABC):
    @abstractmethod
    async def add(self, review: Review) -> Review: ...
    @abstractmethod
    async def list_for_task(self, task_id: uuid.UUID) -> list[Review]: ...


class ProjectMemoryRepository(ABC):
    @abstractmethod
    async def add(self, memory: ProjectMemory) -> ProjectMemory: ...
    @abstractmethod
    async def list_for_project(
        self, project_id: uuid.UUID, category: MemoryCategory | None = None, limit: int = 100
    ) -> list[ProjectMemory]: ...
    @abstractmethod
    async def count_for_project(self, project_id: uuid.UUID) -> int: ...
    @abstractmethod
    async def delete_many(self, memory_ids: list[uuid.UUID]) -> None: ...


class LLMCallRepository(ABC):
    @abstractmethod
    async def add(self, record: LLMCallRecord) -> None: ...
    @abstractmethod
    async def agent_stats(self) -> list[dict[str, Any]]:
        """Aggregates per agent: calls, tokens, avg latency."""
        ...


class NotificationRepository(ABC):
    @abstractmethod
    async def add(self, notification: Notification) -> Notification: ...
    @abstractmethod
    async def list_for_user(
        self, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
    ) -> tuple[list[Notification], int]: ...
    @abstractmethod
    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID | None) -> None:
        """notification_id None = mark all."""
        ...
