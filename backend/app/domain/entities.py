"""Domain entities — plain dataclasses, no framework imports.

Repositories map these to/from persistence models; services and the orchestrator
operate exclusively on these types.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.value_objects import (
    MemoryCategory,
    MessageType,
    NotificationType,
    ProjectStatus,
    TaskStatus,
    UserRole,
    VerdictType,
    WorkflowStatus,
)


@dataclass
class User:
    id: uuid.UUID
    email: str
    password_hash: str
    full_name: str
    role: UserRole = UserRole.MEMBER
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class AgentProfile:
    id: uuid.UUID
    key: str
    name: str
    role_title: str
    personality: str
    system_prompt: str
    provider: str
    model: str
    config: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


@dataclass
class Project:
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    prompt: str
    status: ProjectStatus = ProjectStatus.PENDING
    token_budget: int = 2_000_000
    tokens_used: int = 0
    cost_usd: float = 0.0
    human_in_loop: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Workflow:
    id: uuid.UUID
    project_id: uuid.UUID
    status: WorkflowStatus = WorkflowStatus.PENDING
    dag: dict[str, Any] = field(default_factory=dict)
    current_stage: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    paused_reason: str | None = None
    deadline_at: datetime | None = None


@dataclass
class Task:
    id: uuid.UUID
    project_id: uuid.UUID
    workflow_id: uuid.UUID
    agent_id: uuid.UUID
    node_key: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0
    revision_round: int = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    depends_on: list[uuid.UUID] = field(default_factory=list)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class AgentMessage:
    id: uuid.UUID
    project_id: uuid.UUID
    message_type: MessageType
    content: str
    task_id: uuid.UUID | None = None
    sender_agent_id: uuid.UUID | None = None
    recipient_agent_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class Artifact:
    id: uuid.UUID
    project_id: uuid.UUID
    path: str
    language: str = "text"
    latest_version: int = 1
    created_by_task_id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass
class ArtifactVersion:
    id: uuid.UUID
    artifact_id: uuid.UUID
    version: int
    content: str
    content_hash: str
    size_bytes: int
    validation: dict[str, Any] = field(default_factory=dict)
    created_by_task_id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass
class Review:
    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID
    reviewer_agent_id: uuid.UUID
    verdict: VerdictType
    reasons: list[dict[str, Any]] = field(default_factory=list)
    round: int = 0
    created_at: datetime | None = None


@dataclass
class ProjectMemory:
    id: uuid.UUID
    project_id: uuid.UUID
    category: MemoryCategory
    content: str
    source_task_id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass
class LLMCallRecord:
    id: uuid.UUID
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    status: str = "ok"
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    error: str | None = None
    created_at: datetime | None = None


@dataclass
class Notification:
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    body: str = ""
    project_id: uuid.UUID | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None
