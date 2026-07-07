"""Task detail + manual retry of failed/dead-letter tasks."""
import uuid

from fastapi import APIRouter

from app.application.services.project_service import ProjectService
from app.core.errors import ConflictError, NotFoundError
from app.domain.value_objects import TaskStatus
from app.infrastructure.db.repositories import (
    SqlAgentRepository,
    SqlMessageRepository,
    SqlReviewRepository,
    SqlTaskRepository,
)
from app.infrastructure.redis.queue import get_task_queue
from app.presentation.deps import CurrentUser, DbSession
from app.presentation.schemas.projects import MessageResponse, ReviewInfo, TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _get_task_checked(session, task_id: uuid.UUID, user):
    task = await SqlTaskRepository(session).get(task_id)
    if task is None:
        raise NotFoundError("Task not found")
    await ProjectService(session).get_owned(task.project_id, user)  # authz
    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, session: DbSession, user: CurrentUser) -> TaskResponse:
    task = await _get_task_checked(session, task_id, user)
    agents = {a.id: a for a in await SqlAgentRepository(session).list_active()}
    reviews = await SqlReviewRepository(session).list_for_task(task_id)
    return TaskResponse(
        id=task.id, project_id=task.project_id, node_key=task.node_key, title=task.title,
        description=task.description, status=task.status.value,
        agent_key=agents[task.agent_id].key if task.agent_id in agents else "",
        agent_name=agents[task.agent_id].name if task.agent_id in agents else "",
        attempt=task.attempt, revision_round=task.revision_round, output=task.output,
        error=task.error, depends_on=task.depends_on, queued_at=task.queued_at,
        started_at=task.started_at, finished_at=task.finished_at, created_at=task.created_at,
        reviews=[
            ReviewInfo(verdict=r.verdict.value, reasons=r.reasons, round=r.round,
                       created_at=r.created_at)
            for r in reviews
        ],
    )


@router.get("/{task_id}/messages", response_model=list[MessageResponse])
async def task_messages(
    task_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> list[MessageResponse]:
    task = await _get_task_checked(session, task_id, user)
    messages = await SqlMessageRepository(session).list_for_task(task.id)
    agents = {a.id: a for a in await SqlAgentRepository(session).list_active()}

    def key(agent_id):
        return agents[agent_id].key if agent_id and agent_id in agents else None

    def name(agent_id):
        return agents[agent_id].name if agent_id and agent_id in agents else None

    return [
        MessageResponse(
            id=m.id, project_id=m.project_id, task_id=m.task_id,
            sender_agent_key=key(m.sender_agent_id), sender_name=name(m.sender_agent_id),
            recipient_agent_key=key(m.recipient_agent_id),
            recipient_name=name(m.recipient_agent_id),
            seq=m.seq, message_type=m.message_type.value, content=m.content,
            payload=m.payload, created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: uuid.UUID, session: DbSession, user: CurrentUser) -> TaskResponse:
    task = await _get_task_checked(session, task_id, user)
    if task.status not in (TaskStatus.FAILED, TaskStatus.DEAD_LETTER):
        raise ConflictError(f"Task is '{task.status.value}', only failed or dead_letter "
                            "tasks can be retried")
    repo = SqlTaskRepository(session)
    await repo.update_fields(task.id, status=TaskStatus.QUEUED.value, attempt=0, error=None)
    await session.commit()
    await get_task_queue().enqueue_agent_task(task.id)
    refreshed = await repo.get(task.id)
    assert refreshed is not None
    agents = {a.id: a for a in await SqlAgentRepository(session).list_active()}
    return TaskResponse(
        id=refreshed.id, project_id=refreshed.project_id, node_key=refreshed.node_key,
        title=refreshed.title, description=refreshed.description,
        status=refreshed.status.value,
        agent_key=agents[refreshed.agent_id].key if refreshed.agent_id in agents else "",
        agent_name=agents[refreshed.agent_id].name if refreshed.agent_id in agents else "",
        attempt=refreshed.attempt, revision_round=refreshed.revision_round,
        output=refreshed.output, error=refreshed.error, depends_on=refreshed.depends_on,
        queued_at=refreshed.queued_at, started_at=refreshed.started_at,
        finished_at=refreshed.finished_at, created_at=refreshed.created_at,
    )
