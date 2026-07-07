"""Application services against the real DB layer (SQLite)."""
import uuid
import zipfile
from io import BytesIO

import pytest

from app.application.services.artifact_service import ArtifactService
from app.application.services.auth_service import AuthService
from app.application.services.memory_service import MAX_PROJECT_MEMORIES, MemoryService
from app.application.services.notification_service import NotificationService
from app.application.services.project_service import ProjectService
from app.core.errors import (
    ConflictError,
    EmailTakenError,
    ForbiddenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    NotFoundError,
)
from app.domain.value_objects import (
    GeneratedFile,
    MemoryCategory,
    NotificationType,
    UserRole,
)
from app.infrastructure.db.engine import session_scope
from app.infrastructure.llm.gateway import get_llm_gateway


class TestAuthService:
    async def test_register_login_roundtrip(self, db):
        async with session_scope() as session:
            service = AuthService(session)
            user = await service.register("New@Example.com", "hunter22", "New User")
            assert user.email == "new@example.com"  # normalized
            pair = await service.login("new@example.com", "hunter22")
            assert pair.access_token and pair.refresh_token

    async def test_duplicate_email_rejected(self, db):
        async with session_scope() as session:
            service = AuthService(session)
            await service.register("dup@example.com", "hunter22", "One")
            with pytest.raises(EmailTakenError):
                await service.register("dup@example.com", "other", "Two")

    async def test_wrong_password_rejected(self, db):
        async with session_scope() as session:
            service = AuthService(session)
            await service.register("a@example.com", "hunter22", "A")
            with pytest.raises(InvalidCredentialsError):
                await service.login("a@example.com", "wrong")

    async def test_refresh_rotation(self, db):
        async with session_scope() as session:
            service = AuthService(session)
            await service.register("r@example.com", "hunter22", "R")
            pair = await service.login("r@example.com", "hunter22")
            rotated = await service.refresh(pair.refresh_token)
            assert rotated.refresh_token != pair.refresh_token
            # The used token was revoked and cannot be replayed.
            with pytest.raises(InvalidRefreshTokenError):
                await service.refresh(pair.refresh_token)
            # The rotated one still works.
            await service.refresh(rotated.refresh_token)

    async def test_logout_revokes(self, db):
        async with session_scope() as session:
            service = AuthService(session)
            await service.register("l@example.com", "hunter22", "L")
            pair = await service.login("l@example.com", "hunter22")
            await service.logout(pair.refresh_token)
            with pytest.raises(InvalidRefreshTokenError):
                await service.refresh(pair.refresh_token)


class TestProjectService:
    async def test_owner_isolation(self, make_user, make_project):
        owner = await make_user("owner@example.com")
        stranger = await make_user("stranger@example.com")
        admin = await make_user("admin@example.com", role=UserRole.ADMIN)
        project = await make_project(owner)

        async with session_scope() as session:
            service = ProjectService(session)
            assert (await service.get_owned(project.id, owner)).id == project.id
            assert (await service.get_owned(project.id, admin)).id == project.id
            with pytest.raises(ForbiddenError):
                await service.get_owned(project.id, stranger)
            with pytest.raises(NotFoundError):
                await service.get_owned(uuid.uuid4(), owner)

    async def test_list_visible_scoped_by_role(self, make_user, make_project):
        owner = await make_user("owner@example.com")
        other = await make_user("other@example.com")
        admin = await make_user("admin@example.com", role=UserRole.ADMIN)
        await make_project(owner)
        await make_project(other)

        async with session_scope() as session:
            service = ProjectService(session)
            _, owner_total = await service.list_visible(owner, limit=10, offset=0)
            _, admin_total = await service.list_visible(admin, limit=10, offset=0)
        assert owner_total == 1
        assert admin_total == 2

    async def test_raise_budget_must_exceed_usage(self, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner, token_budget=100)
        async with session_scope() as session:
            from app.infrastructure.db.repositories import SqlProjectRepository

            await SqlProjectRepository(session).update_fields(project.id, tokens_used=100)
        async with session_scope() as session:
            service = ProjectService(session)
            with pytest.raises(ConflictError):
                await service.raise_budget(project.id, owner, 50)
            await service.raise_budget(project.id, owner, 500)
        async with session_scope() as session:
            refreshed = await ProjectService(session).get_owned(project.id, owner)
        assert refreshed.token_budget == 500

    async def test_update_ignores_disallowed_fields(self, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        async with session_scope() as session:
            updated = await ProjectService(session).update(
                project.id, owner, name="Renamed", status="completed"
            )
        assert updated.name == "Renamed"
        assert updated.status.value == "pending"  # status is not user-writable


class TestArtifactService:
    async def test_versioning_and_dedupe(self, make_user, make_project, fake_bus, fake_queue):
        owner = await make_user()
        project = await make_project(owner)
        file_v1 = GeneratedFile(path="src/app.py", content="print('v1')\n", language="python")

        async with session_scope() as session:
            service = ArtifactService(session, fake_bus, fake_queue)
            saved = await service.save_files(project.id, [file_v1])
            assert saved[0]["version"] == 1 and saved[0]["validation_ok"]

            # Identical content → no new version, no event noise.
            assert await service.save_files(project.id, [file_v1]) == []

            # Changed content → version 2.
            file_v2 = GeneratedFile(path="src/app.py", content="print('v2')\n",
                                    language="python")
            saved = await service.save_files(project.id, [file_v2])
            assert saved[0]["version"] == 2

        created = [e for e in fake_bus.events if e[1] == "artifact.created"]
        assert len(created) == 2
        assert len(fake_queue.embeddings) == 2

    async def test_validation_issues_recorded_but_stored(self, make_user, make_project,
                                                         fake_bus):
        owner = await make_user()
        project = await make_project(owner)
        bad = GeneratedFile(path="broken.py", content="def f(:\n", language="python")
        async with session_scope() as session:
            saved = await ArtifactService(session, fake_bus).save_files(project.id, [bad])
        assert saved[0]["validation_ok"] is False
        assert saved[0]["issues"]

    async def test_build_zip_contains_latest_versions(self, make_user, make_project,
                                                      fake_bus):
        owner = await make_user()
        project = await make_project(owner)
        async with session_scope() as session:
            service = ArtifactService(session, fake_bus)
            await service.save_files(project.id, [
                GeneratedFile(path="README.md", content="# v1", language="markdown"),
            ])
            await service.save_files(project.id, [
                GeneratedFile(path="README.md", content="# v2", language="markdown"),
                GeneratedFile(path="src/main.py", content="x = 1\n", language="python"),
            ])
            data = await service.build_zip(project.id)

        with zipfile.ZipFile(BytesIO(data)) as zf:
            assert sorted(zf.namelist()) == ["README.md", "src/main.py"]
            assert zf.read("README.md").decode() == "# v2"


class TestMemoryService:
    async def test_record_and_recall_decisions(self, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        gateway = get_llm_gateway()
        async with session_scope() as session:
            service = MemoryService(session, gateway)
            await service.record_decisions(
                project.id, ["Use PostgreSQL for persistence", "  ", "JWT for auth"]
            )
            memories = await service.project_context(project.id)
        assert len(memories) == 2  # blank decision skipped
        assert all(m.category == MemoryCategory.DECISION for m in memories)

    async def test_consolidation_keeps_tier2_bounded(self, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        gateway = get_llm_gateway()
        async with session_scope() as session:
            service = MemoryService(session, gateway)
            for i in range(0, MAX_PROJECT_MEMORIES + 4, 4):
                await service.record_decisions(
                    project.id, [f"decision {i + j}" for j in range(4)]
                )
            count = await service.repo.count_for_project(project.id)
            summaries = await service.repo.list_for_project(
                project.id, category=MemoryCategory.SUMMARY
            )
        assert count <= MAX_PROJECT_MEMORIES + 4
        assert summaries, "oldest decisions should be merged into a summary row"
        assert "Consolidated earlier decisions" in summaries[0].content

    async def test_semantic_store_and_recall(self, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        gateway = get_llm_gateway()
        async with session_scope() as session:
            service = MemoryService(session, gateway)
            ref = uuid.uuid4()
            await service.embed_and_store(
                project.id, "artifact", ref, "postgres database schema with users table"
            )
            hits = await service.semantic_recall(
                project.id, "postgres database schema with users table"
            )
        assert hits and hits[0].similarity > 0.9

    async def test_recall_failure_returns_empty(self, make_user, make_project, monkeypatch):
        owner = await make_user()
        project = await make_project(owner)
        gateway = get_llm_gateway()

        async def boom(_texts):
            raise RuntimeError("embedding provider down")

        monkeypatch.setattr(gateway, "embed", boom)
        async with session_scope() as session:
            service = MemoryService(session, gateway)
            assert await service.semantic_recall(project.id, "anything") == []


class TestNotificationService:
    async def test_notify_persists_and_publishes(self, make_user, fake_bus):
        user = await make_user()
        async with session_scope() as session:
            service = NotificationService(session, fake_bus)
            note = await service.notify(
                user.id, NotificationType.NEEDS_ATTENTION, "Attention", "Budget hit",
            )
        assert note.title == "Attention"
        assert any(t == "notification" for _, t, _ in fake_bus.events)
