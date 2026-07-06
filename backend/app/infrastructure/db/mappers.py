"""ORM ↔ domain entity mapping."""
from app.domain import entities as e
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
from app.infrastructure.db import models as m


def user_to_domain(row: m.UserModel) -> e.User:
    return e.User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        full_name=row.full_name,
        role=UserRole(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def agent_to_domain(row: m.AgentModel) -> e.AgentProfile:
    return e.AgentProfile(
        id=row.id,
        key=row.key,
        name=row.name,
        role_title=row.role_title,
        personality=row.personality,
        system_prompt=row.system_prompt,
        provider=row.provider,
        model=row.model,
        config=row.config or {},
        is_active=row.is_active,
    )


def project_to_domain(row: m.ProjectModel) -> e.Project:
    return e.Project(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        prompt=row.prompt,
        status=ProjectStatus(row.status),
        token_budget=row.token_budget,
        tokens_used=row.tokens_used,
        cost_usd=float(row.cost_usd),
        human_in_loop=row.human_in_loop,
        settings=row.settings or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def workflow_to_domain(row: m.WorkflowModel) -> e.Workflow:
    return e.Workflow(
        id=row.id,
        project_id=row.project_id,
        status=WorkflowStatus(row.status),
        dag=row.dag or {},
        current_stage=row.current_stage,
        started_at=row.started_at,
        finished_at=row.finished_at,
        paused_reason=row.paused_reason,
        deadline_at=row.deadline_at,
    )


def task_to_domain(row: m.TaskModel, depends_on: list | None = None) -> e.Task:
    return e.Task(
        id=row.id,
        project_id=row.project_id,
        workflow_id=row.workflow_id,
        agent_id=row.agent_id,
        node_key=row.node_key,
        title=row.title,
        description=row.description,
        status=TaskStatus(row.status),
        attempt=row.attempt,
        revision_round=row.revision_round,
        output=row.output,
        error=row.error,
        depends_on=depends_on or [],
        queued_at=row.queued_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )


def message_to_domain(row: m.AgentMessageModel) -> e.AgentMessage:
    return e.AgentMessage(
        id=row.id,
        project_id=row.project_id,
        message_type=MessageType(row.message_type),
        content=row.content,
        task_id=row.task_id,
        sender_agent_id=row.sender_agent_id,
        recipient_agent_id=row.recipient_agent_id,
        correlation_id=row.correlation_id,
        seq=row.seq,
        payload=row.payload or {},
        created_at=row.created_at,
    )


def artifact_to_domain(row: m.ArtifactModel) -> e.Artifact:
    return e.Artifact(
        id=row.id,
        project_id=row.project_id,
        path=row.path,
        language=row.language,
        latest_version=row.latest_version,
        created_by_task_id=row.created_by_task_id,
        created_at=row.created_at,
    )


def artifact_version_to_domain(row: m.ArtifactVersionModel) -> e.ArtifactVersion:
    return e.ArtifactVersion(
        id=row.id,
        artifact_id=row.artifact_id,
        version=row.version,
        content=row.content,
        content_hash=row.content_hash,
        size_bytes=row.size_bytes,
        validation=row.validation or {},
        created_by_task_id=row.created_by_task_id,
        created_at=row.created_at,
    )


def review_to_domain(row: m.ReviewModel) -> e.Review:
    return e.Review(
        id=row.id,
        project_id=row.project_id,
        task_id=row.task_id,
        reviewer_agent_id=row.reviewer_agent_id,
        verdict=VerdictType(row.verdict),
        reasons=row.reasons or [],
        round=row.round,
        created_at=row.created_at,
    )


def memory_to_domain(row: m.ProjectMemoryModel) -> e.ProjectMemory:
    return e.ProjectMemory(
        id=row.id,
        project_id=row.project_id,
        category=MemoryCategory(row.category),
        content=row.content,
        source_task_id=row.source_task_id,
        created_at=row.created_at,
    )


def notification_to_domain(row: m.NotificationModel) -> e.Notification:
    return e.Notification(
        id=row.id,
        user_id=row.user_id,
        type=NotificationType(row.type),
        title=row.title,
        body=row.body,
        project_id=row.project_id,
        read_at=row.read_at,
        created_at=row.created_at,
    )
