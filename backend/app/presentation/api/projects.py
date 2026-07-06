"""Project endpoints: CRUD, workflow control, timeline, messages, artifacts, download."""
import uuid

from fastapi import APIRouter, Query, Request, Response, status

from app.application.services.artifact_service import ArtifactService
from app.application.services.project_service import ProjectService
from app.core.config import get_settings
from app.domain.entities import Project
from app.infrastructure.db.repositories import (
    SqlAgentRepository,
    SqlMessageRepository,
    SqlTaskRepository,
    SqlWorkflowRepository,
)
from app.infrastructure.redis.event_bus import get_event_bus
from app.infrastructure.redis.queue import get_task_queue
from app.infrastructure.redis.rate_limiter import enforce_rate_limit
from app.presentation.deps import CurrentUser, DbSession
from app.presentation.schemas.common import Page
from app.presentation.schemas.projects import (
    ApprovalRequest,
    ArtifactResponse,
    MessageResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    ResumeRequest,
    TaskResponse,
    WorkflowInfo,
)

router = APIRouter(prefix="/projects", tags=["projects"])


async def _to_response(session, project: Project) -> ProjectResponse:
    workflow = await SqlWorkflowRepository(session).get_by_project(project.id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        prompt=project.prompt,
        status=project.status.value,
        token_budget=project.token_budget,
        tokens_used=project.tokens_used,
        cost_usd=project.cost_usd,
        human_in_loop=project.human_in_loop,
        workflow=WorkflowInfo(
            id=workflow.id,
            status=workflow.status.value,
            current_stage=workflow.current_stage,
            started_at=workflow.started_at,
            finished_at=workflow.finished_at,
            paused_reason=workflow.paused_reason,
            deadline_at=workflow.deadline_at,
        ) if workflow else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: Request, body: ProjectCreateRequest, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    settings = get_settings()
    await enforce_rate_limit(
        f"project_create:{user.id}",
        settings.project_create_rate_limit,
        settings.project_create_rate_window,
    )
    project = await ProjectService(session).create(
        user,
        name=body.name,
        prompt=body.prompt,
        token_budget=body.token_budget,
        human_in_loop=body.human_in_loop,
        settings_override=body.settings,
    )
    await session.commit()  # project must be visible to the worker before enqueue
    await get_task_queue().enqueue_workflow_start(project.id)
    return await _to_response(session, project)


@router.get("", response_model=Page[ProjectResponse])
async def list_projects(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ProjectResponse]:
    projects, total = await ProjectService(session).list_visible(user, limit, offset)
    items = [await _to_response(session, p) for p in projects]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    project = await ProjectService(session).get_owned(project_id, user)
    return await _to_response(session, project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdateRequest, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    project = await ProjectService(session).update(
        project_id, user, **body.model_dump(exclude_unset=True)
    )
    return await _to_response(session, project)


@router.post("/{project_id}/cancel", response_model=ProjectResponse)
async def cancel_project(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    service = ProjectService(session)
    await service.get_owned(project_id, user)
    await session.commit()
    from app.application.orchestration.orchestrator import get_orchestrator

    await get_orchestrator().cancel_workflow(project_id)
    project = await service.get_owned(project_id, user)
    return await _to_response(session, project)


@router.post("/{project_id}/resume", response_model=ProjectResponse)
async def resume_project(
    project_id: uuid.UUID, body: ResumeRequest, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    service = ProjectService(session)
    await service.raise_budget(project_id, user, body.token_budget)
    await session.commit()
    from app.application.orchestration.orchestrator import get_orchestrator

    await get_orchestrator().resume_workflow(project_id)
    project = await service.get_owned(project_id, user)
    return await _to_response(session, project)


@router.post("/{project_id}/approve", response_model=ProjectResponse)
async def approve_gate(
    project_id: uuid.UUID, body: ApprovalRequest, session: DbSession, user: CurrentUser
) -> ProjectResponse:
    service = ProjectService(session)
    await service.get_owned(project_id, user)
    await session.commit()
    from app.application.orchestration.orchestrator import get_orchestrator

    await get_orchestrator().apply_human_approval(
        project_id, body.gate, body.approved, body.feedback
    )
    project = await service.get_owned(project_id, user)
    return await _to_response(session, project)


@router.get("/{project_id}/timeline")
async def project_timeline(project_id: uuid.UUID, session: DbSession, user: CurrentUser):
    return await ProjectService(session).timeline(project_id, user)


@router.get("/{project_id}/tasks", response_model=list[TaskResponse])
async def project_tasks(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[TaskResponse]:
    from app.domain.value_objects import TaskStatus

    await ProjectService(session).get_owned(project_id, user)
    parsed = TaskStatus(status_filter) if status_filter else None
    tasks = await SqlTaskRepository(session).list_for_project(project_id, parsed)
    agents = {a.id: a for a in await SqlAgentRepository(session).list_active()}
    return [
        TaskResponse(
            id=t.id, project_id=t.project_id, node_key=t.node_key, title=t.title,
            description=t.description, status=t.status.value,
            agent_key=agents[t.agent_id].key if t.agent_id in agents else "",
            agent_name=agents[t.agent_id].name if t.agent_id in agents else "",
            attempt=t.attempt, revision_round=t.revision_round, output=t.output,
            error=t.error, depends_on=t.depends_on, queued_at=t.queued_at,
            started_at=t.started_at, finished_at=t.finished_at, created_at=t.created_at,
        )
        for t in tasks
    ]


@router.get("/{project_id}/messages", response_model=Page[MessageResponse])
async def project_messages(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    after_seq: int | None = Query(default=None, ge=0),
) -> Page[MessageResponse]:
    await ProjectService(session).get_owned(project_id, user)
    messages, total = await SqlMessageRepository(session).list_for_project(
        project_id, limit, offset, after_seq
    )
    agents = {a.id: a for a in await SqlAgentRepository(session).list_active()}

    def agent_key(agent_id):
        return agents[agent_id].key if agent_id and agent_id in agents else None

    def agent_name(agent_id):
        return agents[agent_id].name if agent_id and agent_id in agents else None

    items = [
        MessageResponse(
            id=msg.id, project_id=msg.project_id, task_id=msg.task_id,
            sender_agent_key=agent_key(msg.sender_agent_id),
            sender_name=agent_name(msg.sender_agent_id),
            recipient_agent_key=agent_key(msg.recipient_agent_id),
            recipient_name=agent_name(msg.recipient_agent_id),
            seq=msg.seq, message_type=msg.message_type.value, content=msg.content,
            payload=msg.payload, created_at=msg.created_at,
        )
        for msg in messages
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{project_id}/artifacts", response_model=list[ArtifactResponse])
async def project_artifacts(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> list[ArtifactResponse]:
    await ProjectService(session).get_owned(project_id, user)
    from app.infrastructure.db.repositories import SqlArtifactRepository

    pairs = await SqlArtifactRepository(session).latest_versions_for_project(project_id)
    return [
        ArtifactResponse(
            id=artifact.id, path=artifact.path, language=artifact.language,
            latest_version=artifact.latest_version, size_bytes=version.size_bytes,
            validation_ok=version.validation.get("ok"), updated_at=version.created_at,
        )
        for artifact, version in pairs
    ]


@router.get("/{project_id}/download")
async def download_project(
    project_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> Response:
    project = await ProjectService(session).get_owned(project_id, user)
    data = await ArtifactService(session, get_event_bus()).build_zip(project_id)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in project.name)[:60]
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name or "project"}.zip"'},
    )
