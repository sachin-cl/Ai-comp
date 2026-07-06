"""SQLAlchemy implementations of the domain repository ports.

Each repository takes an AsyncSession; transaction boundaries are owned by the caller
(session_scope in services / API deps).
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import entities as e
from app.domain.ports import repositories as ports
from app.domain.value_objects import MemoryCategory, ProjectStatus, TaskStatus, WorkflowStatus
from app.infrastructure.db import mappers
from app.infrastructure.db import models as m


class SqlUserRepository(ports.UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user: e.User) -> e.User:
        row = m.UserModel(
            id=user.id,
            email=user.email.lower(),
            password_hash=user.password_hash,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.user_to_domain(row)

    async def get(self, user_id: uuid.UUID) -> e.User | None:
        row = await self.session.get(m.UserModel, user_id)
        return mappers.user_to_domain(row) if row else None

    async def get_by_email(self, email: str) -> e.User | None:
        result = await self.session.execute(
            select(m.UserModel).where(m.UserModel.email == email.lower())
        )
        row = result.scalar_one_or_none()
        return mappers.user_to_domain(row) if row else None

    async def save_refresh_token(
        self, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> None:
        self.session.add(
            m.RefreshTokenModel(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        )
        await self.session.flush()

    async def get_refresh_token_user(self, token_hash: str) -> e.User | None:
        result = await self.session.execute(
            select(m.UserModel)
            .join(m.RefreshTokenModel, m.RefreshTokenModel.user_id == m.UserModel.id)
            .where(
                m.RefreshTokenModel.token_hash == token_hash,
                m.RefreshTokenModel.revoked_at.is_(None),
                m.RefreshTokenModel.expires_at > func.now(),
                m.UserModel.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return mappers.user_to_domain(row) if row else None

    async def revoke_refresh_token(self, token_hash: str) -> None:
        await self.session.execute(
            update(m.RefreshTokenModel)
            .where(m.RefreshTokenModel.token_hash == token_hash)
            .values(revoked_at=func.now())
        )


class SqlAgentRepository(ports.AgentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, profile: e.AgentProfile) -> e.AgentProfile:
        result = await self.session.execute(
            select(m.AgentModel).where(m.AgentModel.key == profile.key)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = m.AgentModel(id=profile.id, key=profile.key)
            self.session.add(row)
        row.name = profile.name
        row.role_title = profile.role_title
        row.personality = profile.personality
        row.system_prompt = profile.system_prompt
        row.provider = profile.provider
        row.model = profile.model
        row.config = profile.config
        row.is_active = profile.is_active
        await self.session.flush()
        return mappers.agent_to_domain(row)

    async def get_by_key(self, key: str) -> e.AgentProfile | None:
        result = await self.session.execute(select(m.AgentModel).where(m.AgentModel.key == key))
        row = result.scalar_one_or_none()
        return mappers.agent_to_domain(row) if row else None

    async def list_active(self) -> list[e.AgentProfile]:
        result = await self.session.execute(
            select(m.AgentModel).where(m.AgentModel.is_active.is_(True)).order_by(m.AgentModel.key)
        )
        return [mappers.agent_to_domain(r) for r in result.scalars()]


class SqlProjectRepository(ports.ProjectRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, project: e.Project) -> e.Project:
        row = m.ProjectModel(
            id=project.id,
            owner_id=project.owner_id,
            name=project.name,
            prompt=project.prompt,
            status=project.status.value,
            token_budget=project.token_budget,
            human_in_loop=project.human_in_loop,
            settings=project.settings,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.project_to_domain(row)

    async def get(self, project_id: uuid.UUID) -> e.Project | None:
        row = await self.session.get(m.ProjectModel, project_id)
        return mappers.project_to_domain(row) if row else None

    async def list_for_owner(
        self, owner_id: uuid.UUID | None, limit: int, offset: int
    ) -> tuple[list[e.Project], int]:
        query = select(m.ProjectModel)
        count_q = select(func.count(m.ProjectModel.id))
        if owner_id is not None:
            query = query.where(m.ProjectModel.owner_id == owner_id)
            count_q = count_q.where(m.ProjectModel.owner_id == owner_id)
        query = query.order_by(m.ProjectModel.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).scalars().all()
        total = (await self.session.execute(count_q)).scalar_one()
        return [mappers.project_to_domain(r) for r in rows], total

    async def update_status(self, project_id: uuid.UUID, status: ProjectStatus) -> None:
        await self.session.execute(
            update(m.ProjectModel).where(m.ProjectModel.id == project_id)
            .values(status=status.value)
        )

    async def update_fields(self, project_id: uuid.UUID, **fields: Any) -> None:
        await self.session.execute(
            update(m.ProjectModel).where(m.ProjectModel.id == project_id).values(**fields)
        )

    async def add_usage(
        self, project_id: uuid.UUID, tokens: int, cost_usd: float
    ) -> tuple[int, float]:
        result = await self.session.execute(
            update(m.ProjectModel)
            .where(m.ProjectModel.id == project_id)
            .values(
                tokens_used=m.ProjectModel.tokens_used + tokens,
                cost_usd=m.ProjectModel.cost_usd + cost_usd,
            )
            .returning(m.ProjectModel.tokens_used, m.ProjectModel.cost_usd)
        )
        row = result.one()
        return int(row[0]), float(row[1])


class SqlWorkflowRepository(ports.WorkflowRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, workflow: e.Workflow) -> e.Workflow:
        row = m.WorkflowModel(
            id=workflow.id,
            project_id=workflow.project_id,
            status=workflow.status.value,
            dag=workflow.dag,
            current_stage=workflow.current_stage,
            started_at=workflow.started_at,
            deadline_at=workflow.deadline_at,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.workflow_to_domain(row)

    async def get(self, workflow_id: uuid.UUID) -> e.Workflow | None:
        row = await self.session.get(m.WorkflowModel, workflow_id)
        return mappers.workflow_to_domain(row) if row else None

    async def get_by_project(self, project_id: uuid.UUID) -> e.Workflow | None:
        result = await self.session.execute(
            select(m.WorkflowModel).where(m.WorkflowModel.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        return mappers.workflow_to_domain(row) if row else None

    async def update_fields(self, workflow_id: uuid.UUID, **fields: Any) -> None:
        await self.session.execute(
            update(m.WorkflowModel).where(m.WorkflowModel.id == workflow_id).values(**fields)
        )

    async def set_status(
        self, workflow_id: uuid.UUID, status: WorkflowStatus, paused_reason: str | None = None
    ) -> None:
        await self.update_fields(workflow_id, status=status.value, paused_reason=paused_reason)


class SqlTaskRepository(ports.TaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _deps_for(self, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(m.TaskDependencyModel).where(m.TaskDependencyModel.task_id.in_(task_ids))
        )
        deps: dict[uuid.UUID, list[uuid.UUID]] = {}
        for dep in result.scalars():
            deps.setdefault(dep.task_id, []).append(dep.depends_on_task_id)
        return deps

    async def add(self, task: e.Task) -> e.Task:
        row = m.TaskModel(
            id=task.id,
            project_id=task.project_id,
            workflow_id=task.workflow_id,
            agent_id=task.agent_id,
            node_key=task.node_key,
            title=task.title,
            description=task.description,
            status=task.status.value,
            attempt=task.attempt,
            revision_round=task.revision_round,
        )
        self.session.add(row)
        await self.session.flush()
        for dep_id in task.depends_on:
            self.session.add(m.TaskDependencyModel(task_id=task.id, depends_on_task_id=dep_id))
        await self.session.flush()
        return mappers.task_to_domain(row, task.depends_on)

    async def get(self, task_id: uuid.UUID) -> e.Task | None:
        row = await self.session.get(m.TaskModel, task_id)
        if row is None:
            return None
        deps = await self._deps_for([task_id])
        return mappers.task_to_domain(row, deps.get(task_id, []))

    async def list_for_project(
        self, project_id: uuid.UUID, status: TaskStatus | None = None
    ) -> list[e.Task]:
        query = select(m.TaskModel).where(m.TaskModel.project_id == project_id)
        if status is not None:
            query = query.where(m.TaskModel.status == status.value)
        query = query.order_by(m.TaskModel.created_at)
        rows = (await self.session.execute(query)).scalars().all()
        deps = await self._deps_for([r.id for r in rows])
        return [mappers.task_to_domain(r, deps.get(r.id, [])) for r in rows]

    async def list_for_workflow(self, workflow_id: uuid.UUID) -> list[e.Task]:
        rows = (
            await self.session.execute(
                select(m.TaskModel)
                .where(m.TaskModel.workflow_id == workflow_id)
                .order_by(m.TaskModel.created_at)
            )
        ).scalars().all()
        deps = await self._deps_for([r.id for r in rows])
        return [mappers.task_to_domain(r, deps.get(r.id, [])) for r in rows]

    async def update_fields(self, task_id: uuid.UUID, **fields: Any) -> None:
        if "status" in fields and isinstance(fields["status"], TaskStatus):
            fields["status"] = fields["status"].value
        await self.session.execute(
            update(m.TaskModel).where(m.TaskModel.id == task_id).values(**fields)
        )

    async def try_mark_running(self, task_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(m.TaskModel)
            .where(m.TaskModel.id == task_id, m.TaskModel.status == TaskStatus.QUEUED.value)
            .values(status=TaskStatus.RUNNING.value, started_at=func.now())
        )
        return result.rowcount > 0

    async def add_dependency(self, task_id: uuid.UUID, depends_on: uuid.UUID) -> None:
        self.session.add(m.TaskDependencyModel(task_id=task_id, depends_on_task_id=depends_on))
        await self.session.flush()


class SqlMessageRepository(ports.MessageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _next_seq(self) -> int:
        dialect = self.session.bind.dialect.name if self.session.bind else ""
        if dialect == "postgresql":
            result = await self.session.execute(text("SELECT nextval('event_seq')"))
            return int(result.scalar_one())
        # SQLite fallback (tests): max+1
        result = await self.session.execute(select(func.coalesce(func.max(
            m.AgentMessageModel.seq), 0)))
        return int(result.scalar_one()) + 1

    async def add(self, message: e.AgentMessage) -> e.AgentMessage:
        seq = await self._next_seq()
        row = m.AgentMessageModel(
            id=message.id,
            project_id=message.project_id,
            task_id=message.task_id,
            sender_agent_id=message.sender_agent_id,
            recipient_agent_id=message.recipient_agent_id,
            correlation_id=message.correlation_id,
            seq=seq,
            message_type=message.message_type.value,
            content=message.content,
            payload=message.payload,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.message_to_domain(row)

    async def list_for_project(
        self, project_id: uuid.UUID, limit: int, offset: int, after_seq: int | None = None
    ) -> tuple[list[e.AgentMessage], int]:
        query = select(m.AgentMessageModel).where(m.AgentMessageModel.project_id == project_id)
        count_q = select(func.count(m.AgentMessageModel.id)).where(
            m.AgentMessageModel.project_id == project_id
        )
        if after_seq is not None:
            query = query.where(m.AgentMessageModel.seq > after_seq)
        query = query.order_by(m.AgentMessageModel.seq).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).scalars().all()
        total = (await self.session.execute(count_q)).scalar_one()
        return [mappers.message_to_domain(r) for r in rows], total

    async def list_for_task(self, task_id: uuid.UUID) -> list[e.AgentMessage]:
        rows = (
            await self.session.execute(
                select(m.AgentMessageModel)
                .where(m.AgentMessageModel.task_id == task_id)
                .order_by(m.AgentMessageModel.seq)
            )
        ).scalars().all()
        return [mappers.message_to_domain(r) for r in rows]


class SqlArtifactRepository(ports.ArtifactRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_path(self, project_id: uuid.UUID, path: str) -> e.Artifact | None:
        result = await self.session.execute(
            select(m.ArtifactModel).where(
                m.ArtifactModel.project_id == project_id, m.ArtifactModel.path == path
            )
        )
        row = result.scalar_one_or_none()
        return mappers.artifact_to_domain(row) if row else None

    async def get(self, artifact_id: uuid.UUID) -> e.Artifact | None:
        row = await self.session.get(m.ArtifactModel, artifact_id)
        return mappers.artifact_to_domain(row) if row else None

    async def add(self, artifact: e.Artifact) -> e.Artifact:
        row = m.ArtifactModel(
            id=artifact.id,
            project_id=artifact.project_id,
            path=artifact.path,
            language=artifact.language,
            latest_version=artifact.latest_version,
            created_by_task_id=artifact.created_by_task_id,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.artifact_to_domain(row)

    async def list_for_project(self, project_id: uuid.UUID) -> list[e.Artifact]:
        rows = (
            await self.session.execute(
                select(m.ArtifactModel)
                .where(m.ArtifactModel.project_id == project_id)
                .order_by(m.ArtifactModel.path)
            )
        ).scalars().all()
        return [mappers.artifact_to_domain(r) for r in rows]

    async def add_version(self, version: e.ArtifactVersion) -> e.ArtifactVersion:
        row = m.ArtifactVersionModel(
            id=version.id,
            artifact_id=version.artifact_id,
            version=version.version,
            content=version.content,
            content_hash=version.content_hash,
            size_bytes=version.size_bytes,
            validation=version.validation,
            created_by_task_id=version.created_by_task_id,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.artifact_version_to_domain(row)

    async def get_version(
        self, artifact_id: uuid.UUID, version: int
    ) -> e.ArtifactVersion | None:
        result = await self.session.execute(
            select(m.ArtifactVersionModel).where(
                m.ArtifactVersionModel.artifact_id == artifact_id,
                m.ArtifactVersionModel.version == version,
            )
        )
        row = result.scalar_one_or_none()
        return mappers.artifact_version_to_domain(row) if row else None

    async def list_versions(self, artifact_id: uuid.UUID) -> list[e.ArtifactVersion]:
        rows = (
            await self.session.execute(
                select(m.ArtifactVersionModel)
                .where(m.ArtifactVersionModel.artifact_id == artifact_id)
                .order_by(m.ArtifactVersionModel.version.desc())
            )
        ).scalars().all()
        return [mappers.artifact_version_to_domain(r) for r in rows]

    async def latest_versions_for_project(
        self, project_id: uuid.UUID
    ) -> list[tuple[e.Artifact, e.ArtifactVersion]]:
        result = await self.session.execute(
            select(m.ArtifactModel, m.ArtifactVersionModel)
            .join(
                m.ArtifactVersionModel,
                (m.ArtifactVersionModel.artifact_id == m.ArtifactModel.id)
                & (m.ArtifactVersionModel.version == m.ArtifactModel.latest_version),
            )
            .where(m.ArtifactModel.project_id == project_id)
            .order_by(m.ArtifactModel.path)
        )
        return [
            (mappers.artifact_to_domain(a), mappers.artifact_version_to_domain(v))
            for a, v in result.all()
        ]

    async def bump_latest(self, artifact_id: uuid.UUID, version: int) -> None:
        await self.session.execute(
            update(m.ArtifactModel)
            .where(m.ArtifactModel.id == artifact_id)
            .values(latest_version=version)
        )


class SqlReviewRepository(ports.ReviewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, review: e.Review) -> e.Review:
        row = m.ReviewModel(
            id=review.id,
            project_id=review.project_id,
            task_id=review.task_id,
            reviewer_agent_id=review.reviewer_agent_id,
            verdict=review.verdict.value,
            reasons=review.reasons,
            round=review.round,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.review_to_domain(row)

    async def list_for_task(self, task_id: uuid.UUID) -> list[e.Review]:
        rows = (
            await self.session.execute(
                select(m.ReviewModel)
                .where(m.ReviewModel.task_id == task_id)
                .order_by(m.ReviewModel.created_at)
            )
        ).scalars().all()
        return [mappers.review_to_domain(r) for r in rows]


class SqlProjectMemoryRepository(ports.ProjectMemoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, memory: e.ProjectMemory) -> e.ProjectMemory:
        row = m.ProjectMemoryModel(
            id=memory.id,
            project_id=memory.project_id,
            category=memory.category.value,
            content=memory.content,
            source_task_id=memory.source_task_id,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.memory_to_domain(row)

    async def list_for_project(
        self, project_id: uuid.UUID, category: MemoryCategory | None = None, limit: int = 100
    ) -> list[e.ProjectMemory]:
        query = select(m.ProjectMemoryModel).where(
            m.ProjectMemoryModel.project_id == project_id
        )
        if category is not None:
            query = query.where(m.ProjectMemoryModel.category == category.value)
        query = query.order_by(m.ProjectMemoryModel.created_at).limit(limit)
        rows = (await self.session.execute(query)).scalars().all()
        return [mappers.memory_to_domain(r) for r in rows]

    async def count_for_project(self, project_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(m.ProjectMemoryModel.id)).where(
                m.ProjectMemoryModel.project_id == project_id
            )
        )
        return int(result.scalar_one())

    async def delete_many(self, memory_ids: list[uuid.UUID]) -> None:
        if memory_ids:
            await self.session.execute(
                delete(m.ProjectMemoryModel).where(m.ProjectMemoryModel.id.in_(memory_ids))
            )


class SqlLLMCallRepository(ports.LLMCallRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: e.LLMCallRecord) -> None:
        self.session.add(
            m.LLMCallModel(
                id=record.id,
                project_id=record.project_id,
                task_id=record.task_id,
                agent_id=record.agent_id,
                correlation_id=record.correlation_id,
                provider=record.provider,
                model=record.model,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                cost_usd=record.cost_usd,
                latency_ms=record.latency_ms,
                status=record.status,
                error=record.error,
            )
        )
        await self.session.flush()

    async def agent_stats(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(
                m.LLMCallModel.agent_id,
                func.count(m.LLMCallModel.id).label("calls"),
                func.coalesce(
                    func.sum(m.LLMCallModel.prompt_tokens + m.LLMCallModel.completion_tokens), 0
                ).label("total_tokens"),
                func.coalesce(func.avg(m.LLMCallModel.latency_ms), 0).label("avg_latency_ms"),
                func.coalesce(func.sum(m.LLMCallModel.cost_usd), 0).label("cost_usd"),
            )
            .where(m.LLMCallModel.agent_id.is_not(None))
            .group_by(m.LLMCallModel.agent_id)
        )
        return [
            {
                "agent_id": row.agent_id,
                "calls": int(row.calls),
                "total_tokens": int(row.total_tokens),
                "avg_latency_ms": float(row.avg_latency_ms),
                "cost_usd": float(row.cost_usd),
            }
            for row in result.all()
        ]


class SqlNotificationRepository(ports.NotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, notification: e.Notification) -> e.Notification:
        row = m.NotificationModel(
            id=notification.id,
            user_id=notification.user_id,
            project_id=notification.project_id,
            type=notification.type.value,
            title=notification.title,
            body=notification.body,
        )
        self.session.add(row)
        await self.session.flush()
        return mappers.notification_to_domain(row)

    async def list_for_user(
        self, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
    ) -> tuple[list[e.Notification], int]:
        query = select(m.NotificationModel).where(m.NotificationModel.user_id == user_id)
        count_q = select(func.count(m.NotificationModel.id)).where(
            m.NotificationModel.user_id == user_id
        )
        if unread_only:
            query = query.where(m.NotificationModel.read_at.is_(None))
            count_q = count_q.where(m.NotificationModel.read_at.is_(None))
        query = query.order_by(m.NotificationModel.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).scalars().all()
        total = (await self.session.execute(count_q)).scalar_one()
        return [mappers.notification_to_domain(r) for r in rows], total

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID | None) -> None:
        query = (
            update(m.NotificationModel)
            .where(m.NotificationModel.user_id == user_id, m.NotificationModel.read_at.is_(None))
            .values(read_at=func.now())
        )
        if notification_id is not None:
            query = query.where(m.NotificationModel.id == notification_id)
        await self.session.execute(query)
