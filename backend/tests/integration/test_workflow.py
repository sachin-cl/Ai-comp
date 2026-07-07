"""End-to-end orchestrator tests: the full company workflow runs on the mock
provider against SQLite, with tests playing the ARQ worker via drain().

Covers: happy path, idempotency, human-in-the-loop gates, revision routing,
loop limits, task retries → dead letter → resume, budget exhaustion, timeout,
and cancellation — every safety guarantee in Promt.md.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import app.application.orchestration.orchestrator as orch_mod
from app.agents.registry import build_agent as real_build_agent
from app.domain.value_objects import ProjectStatus, TaskStatus, WorkflowStatus
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import (
    SqlArtifactRepository,
    SqlLLMCallRepository,
    SqlMessageRepository,
    SqlProjectRepository,
    SqlReviewRepository,
    SqlTaskRepository,
    SqlWorkflowRepository,
)
from tests.conftest import drain

pytestmark = pytest.mark.usefixtures("seeded_agents")


class ScriptedAgent:
    """Stands in for a real agent and returns a fixed output (or raises)."""

    def __init__(self, output=None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error

    async def execute(self, task, inputs):
        if self.error is not None:
            raise self.error
        return self.output


def rejection(target_node: str = "backend_impl") -> dict:
    return {
        "verdict": "changes_requested",
        "summary": "Changes required.",
        "reasons": [{
            "severity": "high", "area": "api", "target_node": target_node,
            "description": "Endpoint missing", "suggestion": "Add it",
        }],
    }


async def get_project(project_id):
    async with session_scope() as session:
        return await SqlProjectRepository(session).get(project_id)


async def get_workflow(project_id):
    async with session_scope() as session:
        return await SqlWorkflowRepository(session).get_by_project(project_id)


async def get_tasks(project_id):
    async with session_scope() as session:
        return await SqlTaskRepository(session).list_for_project(project_id)


class TestHappyPath:
    async def test_full_workflow_completes(self, orchestrator, fake_queue, fake_bus,
                                           make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)

        await orchestrator.start_workflow(project.id)
        assert fake_queue.agent_tasks, "vision task should be enqueued immediately"
        await drain(orchestrator, fake_queue)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.COMPLETED
        assert refreshed.tokens_used > 0

        workflow = await get_workflow(project.id)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.current_stage == "done"
        assert workflow.finished_at is not None

        tasks = await get_tasks(project.id)
        assert len(tasks) == 13
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

        async with session_scope() as session:
            artifacts = await SqlArtifactRepository(session).list_for_project(project.id)
            messages, total = await SqlMessageRepository(session).list_for_project(
                project.id, limit=500, offset=0
            )
        # Engineers + writer delivered files (frontend, backend, db, devops, docs).
        assert len(artifacts) >= 8
        assert any(a.path == "README.md" for a in artifacts)
        # Kickoff, assignments, results, and completion messages all persisted.
        assert total > 20
        assert any("Kickoff" in m.content for m in messages)
        assert any("complete and approved" in m.content for m in messages)

        # Real-time events flowed for tasks and workflow transitions.
        assert "task.updated" in fake_bus.types()
        assert ("workflow.updated" in fake_bus.types())

        # The LLM ledger recorded per-agent usage.
        async with session_scope() as session:
            stats = await SqlLLMCallRepository(session).agent_stats()
        assert len(stats) >= 12

    async def test_start_workflow_idempotent(self, orchestrator, fake_queue,
                                             make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        first_count = len(await get_tasks(project.id))
        await orchestrator.start_workflow(project.id)  # ARQ re-delivery
        assert len(await get_tasks(project.id)) == first_count == 13

    async def test_two_projects_run_without_interference(self, orchestrator, fake_queue,
                                                         make_user, make_project):
        owner = await make_user()
        project_a = await make_project(owner, name="A", prompt="Build a todo app")
        project_b = await make_project(owner, name="B", prompt="Build a blog")
        await orchestrator.start_workflow(project_a.id)
        await orchestrator.start_workflow(project_b.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        for pid in (project_a.id, project_b.id):
            refreshed = await get_project(pid)
            assert refreshed.status == ProjectStatus.COMPLETED
            tasks = await get_tasks(pid)
            assert len(tasks) == 13
            assert all(t.project_id == pid for t in tasks)


class TestHumanInLoop:
    async def test_gates_pause_for_approval(self, orchestrator, fake_queue,
                                            make_user, make_project):
        owner = await make_user()
        project = await make_project(owner, human_in_loop=True)
        await orchestrator.start_workflow(project.id)

        for gate in ("qa_review", "security_review", "final_approval"):
            await drain(orchestrator, fake_queue)
            refreshed = await get_project(project.id)
            assert refreshed.status == ProjectStatus.REVIEW, f"expected pause at {gate}"
            workflow = await get_workflow(project.id)
            assert gate in (workflow.paused_reason or "")
            await orchestrator.apply_human_approval(project.id, gate, approved=True)

        await drain(orchestrator, fake_queue)
        assert (await get_project(project.id)).status == ProjectStatus.COMPLETED

    async def test_human_rejection_routes_revision(self, orchestrator, fake_queue,
                                                   make_user, make_project):
        owner = await make_user()
        project = await make_project(owner, human_in_loop=True)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue)  # paused at qa_review

        await orchestrator.apply_human_approval(
            project.id, "qa_review", approved=False, feedback="The API is wrong"
        )
        tasks = await get_tasks(project.id)
        revisions = [t for t in tasks if t.revision_round > 0]
        assert any(t.node_key == "backend_impl" for t in revisions)
        assert any(t.node_key == "qa_review" for t in revisions)
        assert any("The API is wrong" in t.description for t in revisions)


class TestRevisions:
    async def test_gate_rejection_routes_and_recovers(self, orchestrator, fake_queue,
                                                      monkeypatch, make_user, make_project):
        qa_calls = {"n": 0}

        def flaky_qa_build(profile, gateway):
            if profile.key == "qa_engineer":
                qa_calls["n"] += 1
                if qa_calls["n"] == 1:
                    return ScriptedAgent(output=rejection("backend_impl"))
            return real_build_agent(profile, gateway)

        monkeypatch.setattr(orch_mod, "build_agent", flaky_qa_build)

        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.COMPLETED

        tasks = await get_tasks(project.id)
        backend_rounds = sorted(
            t.revision_round for t in tasks if t.node_key == "backend_impl"
        )
        qa_rounds = sorted(t.revision_round for t in tasks if t.node_key == "qa_review")
        assert backend_rounds == [0, 1]
        assert qa_rounds == [0, 1]

        async with session_scope() as session:
            rejected_gate = next(
                t for t in tasks if t.node_key == "qa_review" and t.revision_round == 0
            )
            reviews = await SqlReviewRepository(session).list_for_task(rejected_gate.id)
        assert reviews and reviews[0].verdict.value == "changes_requested"

    async def test_revision_loop_limit_pauses(self, orchestrator, fake_queue,
                                              monkeypatch, make_user, make_project):
        def hostile_qa_build(profile, gateway):
            if profile.key == "qa_engineer":
                return ScriptedAgent(output=rejection("backend_impl"))
            return real_build_agent(profile, gateway)

        monkeypatch.setattr(orch_mod, "build_agent", hostile_qa_build)

        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.NEEDS_ATTENTION
        workflow = await get_workflow(project.id)
        assert "Revision loop limit" in (workflow.paused_reason or "")

        # Bounded: qa rounds 0..3 and never more (max_revision_loops = 3).
        qa_rounds = sorted(t.revision_round for t in await get_tasks(project.id)
                           if t.node_key == "qa_review")
        assert qa_rounds == [0, 1, 2, 3]

    async def test_rejection_without_valid_target_pauses(self, orchestrator, fake_queue,
                                                         monkeypatch, make_user,
                                                         make_project):
        def vague_qa_build(profile, gateway):
            if profile.key == "qa_engineer":
                return ScriptedAgent(output=rejection(target_node="nonexistent_node"))
            return real_build_agent(profile, gateway)

        monkeypatch.setattr(orch_mod, "build_agent", vague_qa_build)

        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.NEEDS_ATTENTION
        workflow = await get_workflow(project.id)
        assert "without a valid target node" in (workflow.paused_reason or "")


class TestFailureHandling:
    async def test_task_failure_retries_then_dead_letters(self, orchestrator, fake_queue,
                                                          monkeypatch, make_user,
                                                          make_project):
        def broken_backend_build(profile, gateway):
            if profile.key == "backend_engineer":
                return ScriptedAgent(error=RuntimeError("provider exploded"))
            return real_build_agent(profile, gateway)

        monkeypatch.setattr(orch_mod, "build_agent", broken_backend_build)

        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.NEEDS_ATTENTION

        tasks = await get_tasks(project.id)
        backend = next(t for t in tasks if t.node_key == "backend_impl")
        assert backend.status == TaskStatus.DEAD_LETTER
        assert backend.attempt == 3  # initial run + 2 retries (max_task_retries=2)
        assert "provider exploded" in (backend.error or "")

    async def test_resume_requeues_dead_letters_and_completes(self, orchestrator,
                                                              fake_queue, monkeypatch,
                                                              make_user, make_project):
        attempts = {"n": 0}

        def flaky_backend_build(profile, gateway):
            if profile.key == "backend_engineer":
                attempts["n"] += 1
                if attempts["n"] <= 3:  # fails through dead-letter the first time round
                    return ScriptedAgent(error=RuntimeError("transient outage"))
            return real_build_agent(profile, gateway)

        monkeypatch.setattr(orch_mod, "build_agent", flaky_backend_build)

        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)
        assert (await get_project(project.id)).status == ProjectStatus.NEEDS_ATTENTION

        await orchestrator.resume_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)
        assert (await get_project(project.id)).status == ProjectStatus.COMPLETED

    async def test_budget_exhaustion_pauses(self, orchestrator, fake_queue,
                                            make_user, make_project):
        owner = await make_user()
        project = await make_project(owner, token_budget=10)
        async with session_scope() as session:
            await SqlProjectRepository(session).update_fields(project.id, tokens_used=10)

        await orchestrator.start_workflow(project.id)
        await drain(orchestrator, fake_queue, max_steps=600)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.NEEDS_ATTENTION
        workflow = await get_workflow(project.id)
        assert "budget" in (workflow.paused_reason or "").lower()

    async def test_timeout_pauses(self, orchestrator, fake_queue, make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)
        async with session_scope() as session:
            workflow = await SqlWorkflowRepository(session).get_by_project(project.id)
            await SqlWorkflowRepository(session).update_fields(
                workflow.id, deadline_at=datetime.now(UTC) - timedelta(minutes=1)
            )
        await orchestrator._advance(workflow.id)

        refreshed = await get_project(project.id)
        assert refreshed.status == ProjectStatus.NEEDS_ATTENTION
        assert "time limit" in ((await get_workflow(project.id)).paused_reason or "")


class TestCancel:
    async def test_cancel_stops_everything(self, orchestrator, fake_queue,
                                           make_user, make_project):
        owner = await make_user()
        project = await make_project(owner)
        await orchestrator.start_workflow(project.id)

        await orchestrator.cancel_workflow(project.id)
        assert (await get_project(project.id)).status == ProjectStatus.CANCELLED
        assert (await get_workflow(project.id)).status == WorkflowStatus.CANCELLED

        # Any still-queued tasks are skipped by the worker, not executed.
        pending = list(fake_queue.agent_tasks)
        fake_queue.agent_tasks.clear()
        for task_id in pending:
            await orchestrator.run_agent_task(task_id)
        tasks = await get_tasks(project.id)
        assert not any(t.status == TaskStatus.COMPLETED for t in tasks)

    async def test_cancel_unknown_project_is_noop(self, orchestrator):
        await orchestrator.cancel_workflow(uuid.uuid4())  # no raise
