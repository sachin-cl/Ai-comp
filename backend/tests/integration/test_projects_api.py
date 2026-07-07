"""Projects API: CRUD, workflow control endpoints, tasks, messages, artifacts,
download — driven through the real ASGI app with the worker played by drain().
"""
import io
import zipfile

import pytest

from app.domain.value_objects import GeneratedFile
from app.infrastructure.db.engine import session_scope
from tests.conftest import drain, register_and_login

CREATE = {"name": "Expense Tracker", "prompt": "Build an expense tracker"}


async def create_project(client, headers) -> dict:
    res = await client.post("/api/v1/projects", json=CREATE, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


class TestCrud:
    async def test_create_enqueues_workflow(self, client, auth_headers, fake_queue):
        body = await create_project(client, auth_headers)
        assert body["status"] == "pending"
        assert body["token_budget"] == 2_000_000
        assert [str(p) for p in fake_queue.workflow_starts] == [body["id"]]

    async def test_create_requires_prompt(self, client, auth_headers):
        res = await client.post(
            "/api/v1/projects", json={"name": "X"}, headers=auth_headers
        )
        assert res.status_code == 422

    async def test_list_and_get(self, client, auth_headers):
        created = await create_project(client, auth_headers)
        listing = await client.get("/api/v1/projects", headers=auth_headers)
        assert listing.status_code == 200
        page = listing.json()
        assert page["total"] == 1
        assert page["items"][0]["id"] == created["id"]

        detail = await client.get(f"/api/v1/projects/{created['id']}", headers=auth_headers)
        assert detail.status_code == 200
        assert detail.json()["prompt"] == CREATE["prompt"]

    async def test_other_users_project_forbidden(self, client, auth_headers):
        created = await create_project(client, auth_headers)
        stranger = await register_and_login(client, "stranger@example.com")
        res = await client.get(f"/api/v1/projects/{created['id']}", headers=stranger)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"

    async def test_patch_updates_name(self, client, auth_headers):
        created = await create_project(client, auth_headers)
        res = await client.patch(
            f"/api/v1/projects/{created['id']}",
            json={"name": "Renamed"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["name"] == "Renamed"

    async def test_unknown_project_404(self, client, auth_headers):
        res = await client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000", headers=auth_headers
        )
        assert res.status_code == 404


@pytest.mark.usefixtures("seeded_agents")
class TestWorkflowThroughApi:
    async def run_to_completion(self, client, headers, fake_queue) -> dict:
        project = await create_project(client, headers)
        orch = client.orchestrator
        for project_id in fake_queue.workflow_starts:
            await orch.start_workflow(project_id)
        fake_queue.workflow_starts.clear()
        await drain(orch, fake_queue)
        return project

    async def test_full_flow_visible_through_api(self, client, auth_headers, fake_queue):
        project = await self.run_to_completion(client, auth_headers, fake_queue)
        pid = project["id"]

        detail = (await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)).json()
        assert detail["status"] == "completed"
        assert detail["workflow"]["current_stage"] == "done"
        assert detail["tokens_used"] > 0

        tasks = (await client.get(f"/api/v1/projects/{pid}/tasks",
                                  headers=auth_headers)).json()
        assert len(tasks) == 13
        assert all(t["status"] == "completed" for t in tasks)
        assert all(t["agent_name"] for t in tasks)

        messages = (await client.get(f"/api/v1/projects/{pid}/messages?limit=500",
                                     headers=auth_headers)).json()
        assert messages["total"] > 20
        seqs = [m["seq"] for m in messages["items"]]
        assert seqs == sorted(seqs)

        timeline = (await client.get(f"/api/v1/projects/{pid}/timeline",
                                     headers=auth_headers)).json()
        assert timeline["workflow"]["status"] == "completed"
        assert len(timeline["spans"]) == 13

        artifacts = (await client.get(f"/api/v1/projects/{pid}/artifacts",
                                      headers=auth_headers)).json()
        assert len(artifacts) >= 8
        assert all(a["latest_version"] >= 1 for a in artifacts)

    async def test_task_detail_and_messages(self, client, auth_headers, fake_queue):
        project = await self.run_to_completion(client, auth_headers, fake_queue)
        tasks = (await client.get(f"/api/v1/projects/{project['id']}/tasks",
                                  headers=auth_headers)).json()
        gate = next(t for t in tasks if t["node_key"] == "qa_review")

        detail = (await client.get(f"/api/v1/tasks/{gate['id']}",
                                   headers=auth_headers)).json()
        assert detail["output"]["verdict"] == "approved"
        assert detail["reviews"] and detail["reviews"][0]["verdict"] == "approved"

        messages = (await client.get(f"/api/v1/tasks/{gate['id']}/messages",
                                     headers=auth_headers)).json()
        assert any(m["message_type"] == "assignment" for m in messages)

    async def test_retry_completed_task_conflict(self, client, auth_headers, fake_queue):
        project = await self.run_to_completion(client, auth_headers, fake_queue)
        tasks = (await client.get(f"/api/v1/projects/{project['id']}/tasks",
                                  headers=auth_headers)).json()
        res = await client.post(f"/api/v1/tasks/{tasks[0]['id']}/retry",
                                headers=auth_headers)
        assert res.status_code == 409

    async def test_download_zip(self, client, auth_headers, fake_queue):
        project = await self.run_to_completion(client, auth_headers, fake_queue)
        res = await client.get(f"/api/v1/projects/{project['id']}/download",
                               headers=auth_headers)
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        assert "attachment" in res.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            names = zf.namelist()
        assert "README.md" in names
        assert len(names) >= 8

    async def test_cancel_endpoint(self, client, auth_headers, fake_queue):
        project = await create_project(client, auth_headers)
        await client.orchestrator.start_workflow(fake_queue.workflow_starts.pop())
        res = await client.post(f"/api/v1/projects/{project['id']}/cancel",
                                json={}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"

    async def test_resume_endpoint_raises_budget(self, client, auth_headers, fake_queue):
        project = await create_project(client, auth_headers)
        pid = project["id"]
        import uuid as _uuid

        from app.infrastructure.db.repositories import SqlProjectRepository

        async with session_scope() as session:
            await SqlProjectRepository(session).update_fields(
                _uuid.UUID(pid), tokens_used=20_000, token_budget=20_000
            )
        res = await client.post(f"/api/v1/projects/{pid}/resume",
                                json={"token_budget": 15_000}, headers=auth_headers)
        assert res.status_code == 409  # must exceed tokens already used

        res = await client.post(f"/api/v1/projects/{pid}/resume",
                                json={"token_budget": 100_000}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["token_budget"] == 100_000


class TestArtifactsApi:
    async def test_artifact_content_and_versions(self, client, auth_headers, fake_bus):
        project = await create_project(client, auth_headers)
        import uuid as _uuid

        from app.application.services.artifact_service import ArtifactService

        pid = _uuid.UUID(project["id"])
        async with session_scope() as session:
            service = ArtifactService(session, fake_bus)
            await service.save_files(pid, [
                GeneratedFile(path="src/app.py", content="print('v1')\n", language="python"),
            ])
            await service.save_files(pid, [
                GeneratedFile(path="src/app.py", content="print('v2')\n", language="python"),
            ])

        listing = (await client.get(f"/api/v1/projects/{project['id']}/artifacts",
                                    headers=auth_headers)).json()
        artifact_id = listing[0]["id"]
        assert listing[0]["latest_version"] == 2

        content = (await client.get(f"/api/v1/artifacts/{artifact_id}",
                                    headers=auth_headers)).json()
        assert content["content"] == "print('v2')\n"
        assert content["version"] == 2

        versions = (await client.get(f"/api/v1/artifacts/{artifact_id}/versions",
                                     headers=auth_headers)).json()
        assert [v["version"] for v in versions] == [2, 1]

        old = (await client.get(f"/api/v1/artifacts/{artifact_id}/versions/1",
                                headers=auth_headers)).json()
        assert old["content"] == "print('v1')\n"

    async def test_artifact_of_foreign_project_forbidden(self, client, auth_headers,
                                                         fake_bus):
        project = await create_project(client, auth_headers)
        import uuid as _uuid

        from app.application.services.artifact_service import ArtifactService

        async with session_scope() as session:
            await ArtifactService(session, fake_bus).save_files(
                _uuid.UUID(project["id"]),
                [GeneratedFile(path="secret.py", content="x=1\n", language="python")],
            )
        listing = (await client.get(f"/api/v1/projects/{project['id']}/artifacts",
                                    headers=auth_headers)).json()
        stranger = await register_and_login(client, "stranger@example.com")
        res = await client.get(f"/api/v1/artifacts/{listing[0]['id']}", headers=stranger)
        assert res.status_code == 403
