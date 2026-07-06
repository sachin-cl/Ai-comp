"""Project lifecycle: create → workflow kickoff → cancel/resume/approve → timeline."""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.domain.entities import Project, User
from app.domain.value_objects import ProjectStatus, UserRole
from app.infrastructure.db.repositories import (
    SqlProjectRepository,
    SqlTaskRepository,
    SqlWorkflowRepository,
)


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = SqlProjectRepository(session)
        self.workflows = SqlWorkflowRepository(session)
        self.tasks = SqlTaskRepository(session)

    async def create(
        self,
        owner: User,
        name: str,
        prompt: str,
        token_budget: int | None = None,
        human_in_loop: bool = False,
        settings_override: dict[str, Any] | None = None,
    ) -> Project:
        app_settings = get_settings()
        return await self.projects.add(
            Project(
                id=uuid.uuid4(),
                owner_id=owner.id,
                name=name.strip(),
                prompt=prompt.strip(),
                status=ProjectStatus.PENDING,
                token_budget=token_budget or app_settings.default_token_budget,
                human_in_loop=human_in_loop,
                settings=settings_override or {},
            )
        )

    async def get_owned(self, project_id: uuid.UUID, user: User) -> Project:
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        if project.owner_id != user.id and user.role != UserRole.ADMIN:
            raise ForbiddenError("You do not have access to this project")
        return project

    async def list_visible(
        self, user: User, limit: int, offset: int
    ) -> tuple[list[Project], int]:
        owner_id = None if user.role == UserRole.ADMIN else user.id
        return await self.projects.list_for_owner(owner_id, limit, offset)

    async def update(
        self, project_id: uuid.UUID, user: User, **fields: Any
    ) -> Project:
        project = await self.get_owned(project_id, user)
        allowed = {k: v for k, v in fields.items()
                   if k in {"name", "human_in_loop", "settings", "token_budget"}
                   and v is not None}
        if allowed:
            await self.projects.update_fields(project.id, **allowed)
        updated = await self.projects.get(project.id)
        assert updated is not None
        return updated

    async def raise_budget(self, project_id: uuid.UUID, user: User,
                           new_budget: int | None) -> None:
        project = await self.get_owned(project_id, user)
        if new_budget is not None:
            if new_budget <= project.tokens_used:
                raise ConflictError(
                    "New budget must exceed tokens already used",
                    details={"tokens_used": project.tokens_used},
                )
            await self.projects.update_fields(project.id, token_budget=new_budget)

    async def timeline(self, project_id: uuid.UUID, user: User) -> dict[str, Any]:
        project = await self.get_owned(project_id, user)
        workflow = await self.workflows.get_by_project(project.id)
        tasks = await self.tasks.list_for_project(project.id)
        return {
            "project_id": str(project.id),
            "workflow": {
                "status": workflow.status.value if workflow else "pending",
                "current_stage": workflow.current_stage if workflow else "",
                "started_at": workflow.started_at if workflow else None,
                "finished_at": workflow.finished_at if workflow else None,
                "deadline_at": workflow.deadline_at if workflow else None,
            },
            "spans": [
                {
                    "task_id": str(t.id),
                    "node_key": t.node_key,
                    "title": t.title,
                    "status": t.status.value,
                    "revision_round": t.revision_round,
                    "queued_at": t.queued_at,
                    "started_at": t.started_at,
                    "finished_at": t.finished_at,
                }
                for t in tasks
            ],
        }
