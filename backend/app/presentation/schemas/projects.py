import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    token_budget: int | None = Field(default=None, ge=10_000, le=50_000_000)
    human_in_loop: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    human_in_loop: bool | None = None
    token_budget: int | None = Field(default=None, ge=10_000, le=50_000_000)
    settings: dict[str, Any] | None = None


class WorkflowInfo(BaseModel):
    id: uuid.UUID | None = None
    status: str = "pending"
    current_stage: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    paused_reason: str | None = None
    deadline_at: datetime | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    prompt: str
    status: str
    token_budget: int
    tokens_used: int
    cost_usd: float
    human_in_loop: bool
    workflow: WorkflowInfo | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResumeRequest(BaseModel):
    token_budget: int | None = Field(default=None, ge=10_000, le=50_000_000)


class ApprovalRequest(BaseModel):
    gate: str = Field(pattern=r"^[a-z_]+$")
    approved: bool
    feedback: str = Field(default="", max_length=4000)


class TaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    node_key: str
    title: str
    description: str
    status: str
    agent_key: str = ""
    agent_name: str = ""
    attempt: int
    revision_round: int
    output: dict[str, Any] | None = None
    error: str | None = None
    depends_on: list[uuid.UUID] = Field(default_factory=list)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    sender_agent_key: str | None = None
    sender_name: str | None = None
    recipient_agent_key: str | None = None
    recipient_name: str | None = None
    seq: int
    message_type: str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    path: str
    language: str
    latest_version: int
    size_bytes: int | None = None
    validation_ok: bool | None = None
    updated_at: datetime | None = None


class ArtifactContentResponse(BaseModel):
    id: uuid.UUID
    path: str
    language: str
    version: int
    content: str
    content_hash: str
    size_bytes: int
    validation: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentResponse(BaseModel):
    key: str
    name: str
    role_title: str
    personality: str
    provider: str
    model: str
    is_active: bool


class NotificationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    type: str
    title: str
    body: str
    read_at: datetime | None = None
    created_at: datetime | None = None
