"""Agents, analytics, notifications, and ops endpoints."""
import uuid

import pytest

from app.application.services.notification_service import NotificationService
from app.domain.value_objects import NotificationType
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import SqlUserRepository
from tests.conftest import drain


async def user_id_for(email: str) -> uuid.UUID:
    async with session_scope() as session:
        user = await SqlUserRepository(session).get_by_email(email)
        assert user is not None
        return user.id


@pytest.mark.usefixtures("seeded_agents")
class TestAgentsApi:
    async def test_list_agents(self, client, auth_headers):
        res = await client.get("/api/v1/agents", headers=auth_headers)
        assert res.status_code == 200
        agents = res.json()
        assert len(agents) >= 12
        keys = {a["key"] for a in agents}
        assert {"ceo", "qa_engineer", "marketing_manager"} <= keys
        sample = agents[0]
        assert sample["name"] and sample["role_title"] and sample["provider"]

    async def test_agent_stats_shape(self, client, auth_headers):
        res = await client.get("/api/v1/agents/qa_engineer/stats", headers=auth_headers)
        assert res.status_code == 200
        stats = res.json()
        assert stats["agent_key"] == "qa_engineer"
        assert stats["tasks_total"] == 0  # nothing has run yet

    async def test_agents_require_auth(self, client):
        assert (await client.get("/api/v1/agents")).status_code == 401


@pytest.mark.usefixtures("seeded_agents")
class TestAnalyticsApi:
    async def test_overview_reflects_completed_work(self, client, auth_headers, fake_queue):
        create = await client.post(
            "/api/v1/projects",
            json={"name": "P", "prompt": "Build a blog"},
            headers=auth_headers,
        )
        orch = client.orchestrator
        await orch.start_workflow(uuid.UUID(create.json()["id"]))
        await drain(orch, fake_queue)

        res = await client.get("/api/v1/analytics/overview", headers=auth_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["projects_by_status"].get("completed") == 1
        assert body["total_tokens"] > 0
        busy = [a for a in body["agents"] if a["tasks_completed"] > 0]
        assert len(busy) >= 12
        assert all(a["llm_calls"] > 0 for a in busy)


class TestNotificationsApi:
    async def test_list_mark_read_flow(self, client, auth_headers, fake_bus):
        uid = await user_id_for("owner@example.com")
        async with session_scope() as session:
            service = NotificationService(session, fake_bus)
            await service.notify(uid, NotificationType.NEEDS_ATTENTION, "First")
            await service.notify(uid, NotificationType.WORKFLOW_COMPLETED, "Second")

        res = await client.get("/api/v1/notifications", headers=auth_headers)
        page = res.json()
        assert page["total"] == 2
        assert all(n["read_at"] is None for n in page["items"])

        first_id = page["items"][0]["id"]
        assert (
            await client.post(f"/api/v1/notifications/{first_id}/read", headers=auth_headers)
        ).status_code == 204

        unread = (await client.get("/api/v1/notifications?unread=true",
                                   headers=auth_headers)).json()
        assert unread["total"] == 1

        assert (
            await client.post("/api/v1/notifications/read-all", headers=auth_headers)
        ).status_code == 204
        unread = (await client.get("/api/v1/notifications?unread=true",
                                   headers=auth_headers)).json()
        assert unread["total"] == 0

    async def test_notifications_scoped_to_user(self, client, auth_headers, fake_bus):
        uid = await user_id_for("owner@example.com")
        async with session_scope() as session:
            await NotificationService(session, fake_bus).notify(
                uid, NotificationType.NEEDS_ATTENTION, "Private"
            )
        from tests.conftest import register_and_login

        stranger = await register_and_login(client, "stranger@example.com")
        page = (await client.get("/api/v1/notifications", headers=stranger)).json()
        assert page["total"] == 0


class TestOps:
    async def test_health(self, client):
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    async def test_metrics_exposition(self, client):
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "llm_calls_total" in res.text or "python_info" in res.text

    async def test_security_headers_present(self, client):
        res = await client.get("/health")
        assert res.headers.get("x-content-type-options") == "nosniff"

    async def test_correlation_id_returned(self, client):
        res = await client.get("/health")
        assert res.headers.get("x-correlation-id")
