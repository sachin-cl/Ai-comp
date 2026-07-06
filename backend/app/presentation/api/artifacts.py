"""Artifact content + version history."""
import uuid

from fastapi import APIRouter

from app.application.services.project_service import ProjectService
from app.core.errors import NotFoundError
from app.infrastructure.db.repositories import SqlArtifactRepository
from app.presentation.deps import CurrentUser, DbSession
from app.presentation.schemas.projects import ArtifactContentResponse

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


async def _artifact_checked(session, artifact_id: uuid.UUID, user):
    artifact = await SqlArtifactRepository(session).get(artifact_id)
    if artifact is None:
        raise NotFoundError("Artifact not found")
    await ProjectService(session).get_owned(artifact.project_id, user)
    return artifact


@router.get("/{artifact_id}", response_model=ArtifactContentResponse)
async def get_artifact(
    artifact_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> ArtifactContentResponse:
    artifact = await _artifact_checked(session, artifact_id, user)
    version = await SqlArtifactRepository(session).get_version(
        artifact.id, artifact.latest_version
    )
    if version is None:
        raise NotFoundError("Artifact has no stored versions")
    return ArtifactContentResponse(
        id=artifact.id, path=artifact.path, language=artifact.language,
        version=version.version, content=version.content, content_hash=version.content_hash,
        size_bytes=version.size_bytes, validation=version.validation,
        created_at=version.created_at,
    )


@router.get("/{artifact_id}/versions")
async def list_versions(artifact_id: uuid.UUID, session: DbSession, user: CurrentUser):
    artifact = await _artifact_checked(session, artifact_id, user)
    versions = await SqlArtifactRepository(session).list_versions(artifact.id)
    return [
        {
            "version": v.version,
            "content_hash": v.content_hash,
            "size_bytes": v.size_bytes,
            "validation_ok": v.validation.get("ok"),
            "created_at": v.created_at,
        }
        for v in versions
    ]


@router.get("/{artifact_id}/versions/{version}", response_model=ArtifactContentResponse)
async def get_version(
    artifact_id: uuid.UUID, version: int, session: DbSession, user: CurrentUser
) -> ArtifactContentResponse:
    artifact = await _artifact_checked(session, artifact_id, user)
    row = await SqlArtifactRepository(session).get_version(artifact.id, version)
    if row is None:
        raise NotFoundError(f"Version {version} not found")
    return ArtifactContentResponse(
        id=artifact.id, path=artifact.path, language=artifact.language,
        version=row.version, content=row.content, content_hash=row.content_hash,
        size_bytes=row.size_bytes, validation=row.validation, created_at=row.created_at,
    )
