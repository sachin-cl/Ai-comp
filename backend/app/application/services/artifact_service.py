"""Artifact service: validate → hash → version → store → publish → embed."""
import hashlib
import io
import uuid
import zipfile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.entities import Artifact, ArtifactVersion
from app.domain.ports.event_bus import EventBus
from app.domain.ports.task_queue import TaskQueue
from app.domain.value_objects import GeneratedFile
from app.infrastructure.db.repositories import SqlArtifactRepository
from app.infrastructure.validation.validators import validate_content

logger = get_logger("artifacts")


class ArtifactService:
    def __init__(
        self, session: AsyncSession, event_bus: EventBus, task_queue: TaskQueue | None = None
    ) -> None:
        self.repo = SqlArtifactRepository(session)
        self.event_bus = event_bus
        self.task_queue = task_queue

    async def save_files(
        self,
        project_id: uuid.UUID,
        files: list[GeneratedFile],
        created_by_task_id: uuid.UUID | None = None,
    ) -> list[dict]:
        saved: list[dict] = []
        for file in files:
            entry = await self._save_one(project_id, file, created_by_task_id)
            if entry:
                saved.append(entry)
        return saved

    async def _save_one(
        self,
        project_id: uuid.UUID,
        file: GeneratedFile,
        created_by_task_id: uuid.UUID | None,
    ) -> dict | None:
        content_hash = hashlib.sha256(file.content.encode("utf-8", errors="replace")).hexdigest()
        artifact = await self.repo.get_by_path(project_id, file.path)
        if artifact is not None:
            latest = await self.repo.get_version(artifact.id, artifact.latest_version)
            if latest and latest.content_hash == content_hash:
                return None  # identical content — no noise version
            new_version = artifact.latest_version + 1
        else:
            artifact = await self.repo.add(
                Artifact(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    path=file.path,
                    language=file.language,
                    latest_version=0,
                    created_by_task_id=created_by_task_id,
                )
            )
            new_version = 1

        validation = validate_content(file.path, file.content, file.language)
        version = await self.repo.add_version(
            ArtifactVersion(
                id=uuid.uuid4(),
                artifact_id=artifact.id,
                version=new_version,
                content=file.content,
                content_hash=content_hash,
                size_bytes=len(file.content.encode("utf-8", errors="replace")),
                validation=validation,
                created_by_task_id=created_by_task_id,
            )
        )
        await self.repo.bump_latest(artifact.id, new_version)
        await self.event_bus.publish_project_event(
            project_id,
            "artifact.created",
            {
                "artifact_id": str(artifact.id),
                "path": file.path,
                "version": new_version,
                "language": file.language,
                "validation_ok": validation.get("ok", True),
            },
        )
        if self.task_queue is not None:
            try:
                await self.task_queue.enqueue_embedding(
                    project_id, "artifact", version.id,
                    f"{file.path}\n{file.content[:4000]}",
                )
            except Exception:
                logger.warning("embedding_enqueue_failed", path=file.path, exc_info=True)
        return {
            "path": file.path,
            "version": new_version,
            "validation_ok": validation.get("ok", True),
            "issues": validation.get("issues", []),
        }

    async def build_zip(self, project_id: uuid.UUID) -> bytes:
        """ZIP of the latest version of every artifact."""
        pairs = await self.repo.latest_versions_for_project(project_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for artifact, version in pairs:
                zf.writestr(artifact.path, version.content)
        return buffer.getvalue()
