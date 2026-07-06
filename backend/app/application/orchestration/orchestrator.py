"""Workflow orchestrator: compiles the DAG into tasks, dispatches them through ARQ,
routes review verdicts into bounded revision loops, and enforces every safety limit.

All entry points are idempotent — ARQ may re-deliver jobs after a worker crash.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.prompt_builder import PromptInputs
from app.agents.registry import build_agent
from app.application.orchestration.dag import DAGNode, WorkflowDAG
from app.application.orchestration.templates import (
    REVISABLE_NODES,
    STAGE_ORDER,
    standard_workflow,
)
from app.application.services.artifact_service import ArtifactService
from app.application.services.memory_service import MemoryService
from app.application.services.notification_service import NotificationService
from app.core.config import get_settings
from app.core.errors import BudgetExceededError, MalformedOutputError
from app.core.logging import get_logger, new_correlation_id
from app.core.metrics import AGENT_TASK_DURATION
from app.domain.entities import AgentMessage, Project, Review, Task, Workflow
from app.domain.policies import RevisionLoopPolicy, TaskRetryPolicy, WorkflowTimeoutPolicy
from app.domain.value_objects import (
    GeneratedFile,
    MessageType,
    NotificationType,
    ProjectStatus,
    TaskStatus,
    VerdictType,
    WorkflowStatus,
)
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import (
    SqlAgentRepository,
    SqlMessageRepository,
    SqlProjectRepository,
    SqlReviewRepository,
    SqlTaskRepository,
    SqlWorkflowRepository,
)
from app.infrastructure.llm.gateway import get_llm_gateway
from app.infrastructure.redis.event_bus import get_event_bus
from app.infrastructure.redis.queue import get_task_queue

logger = get_logger("orchestrator")

ACTIVE_WORKFLOW_STATUSES = {WorkflowStatus.PLANNING, WorkflowStatus.IN_PROGRESS}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def humanize_output(agent_key: str, output: dict[str, Any]) -> str:
    """Turn structured output into a chat-readable message body."""
    if "vision" in output:
        return output["vision"]
    if "verdict" in output:
        body = f"Verdict: {output['verdict'].upper()} — {output.get('summary', '')}"
        for reason in output.get("reasons", [])[:5]:
            body += f"\n• [{reason.get('severity')}] {reason.get('description')}"
        return body
    if "files" in output:
        files = ", ".join(f["path"] for f in output["files"][:8])
        more = len(output["files"]) - 8
        suffix = f" (+{more} more)" if more > 0 else ""
        return f"{output.get('summary', 'Delivered files.')}\nFiles: {files}{suffix}"
    if "tagline" in output:
        return f"{output['tagline']}\n{output.get('product_description', '')}"
    if "architecture_overview" in output:
        return output["architecture_overview"]
    if "overview" in output:
        return output["overview"]
    if "wireframes" in output:
        screens = ", ".join(w["screen"] for w in output["wireframes"][:6])
        return f"Design ready. Screens: {screens}"
    return output.get("summary", "Task completed.")


class Orchestrator:
    """Stateless coordinator; every method opens its own transaction scopes."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.event_bus = get_event_bus()
        self.queue = get_task_queue()
        self.gateway = get_llm_gateway()

    # ------------------------------------------------------------- lifecycle

    async def start_workflow(self, project_id: uuid.UUID) -> None:
        dag = standard_workflow()
        async with session_scope() as session:
            projects = SqlProjectRepository(session)
            workflows = SqlWorkflowRepository(session)
            tasks = SqlTaskRepository(session)
            agents = SqlAgentRepository(session)

            project = await projects.get(project_id)
            if project is None:
                logger.warning("start_workflow_missing_project", project_id=str(project_id))
                return
            if await workflows.get_by_project(project_id) is not None:
                return  # idempotent re-delivery

            timeout_minutes = int(
                project.settings.get("workflow_timeout_minutes",
                                     self.settings.workflow_timeout_minutes)
            )
            started_at = _utcnow()
            workflow = await workflows.add(
                Workflow(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    status=WorkflowStatus.IN_PROGRESS,
                    dag=dag.to_dict(),
                    current_stage="vision",
                    started_at=started_at,
                    deadline_at=WorkflowTimeoutPolicy.deadline(started_at, timeout_minutes),
                )
            )
            node_task_ids: dict[str, uuid.UUID] = {}
            for node in dag.nodes.values():
                profile = await agents.get_by_key(node.agent_key)
                if profile is None:
                    raise RuntimeError(f"Agent '{node.agent_key}' not seeded")
                task = await tasks.add(
                    Task(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        workflow_id=workflow.id,
                        agent_id=profile.id,
                        node_key=node.key,
                        title=node.title,
                        description=node.instructions,
                        status=TaskStatus.PENDING,
                        depends_on=[node_task_ids[d] for d in node.inputs
                                    if d in node_task_ids],
                    )
                )
                node_task_ids[node.key] = task.id
            await projects.update_status(project_id, ProjectStatus.IN_PROGRESS)
            await SqlMessageRepository(session).add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    message_type=MessageType.SYSTEM,
                    content=f"Kickoff: the company is now working on “{project.name}”. "
                            f"{len(dag.nodes)} tasks planned.",
                )
            )
        await self.event_bus.publish_project_event(
            project_id, "workflow.updated",
            {"status": "in_progress", "current_stage": "vision"},
        )
        await self._advance(workflow.id)

    # -------------------------------------------------------------- dispatch

    def _latest_by_node(self, tasks: list[Task]) -> dict[str, Task]:
        latest: dict[str, Task] = {}
        for task in tasks:
            current = latest.get(task.node_key)
            if current is None or task.revision_round > current.revision_round:
                latest[task.node_key] = task
        return latest

    def _node_satisfied(self, node: DAGNode, latest: dict[str, Task],
                        human_in_loop: bool) -> bool:
        task = latest.get(node.key)
        if task is None or task.status != TaskStatus.COMPLETED:
            return False
        if node.is_gate:
            output = task.output or {}
            if output.get("verdict") != VerdictType.APPROVED.value:
                return False
            if human_in_loop and not output.get("human_approved"):
                return False
        return True

    async def _advance(self, workflow_id: uuid.UUID) -> None:
        """Re-scan the DAG; enqueue every unblocked node; detect completion/timeout."""
        to_enqueue: list[uuid.UUID] = []
        completed_project: Project | None = None
        async with session_scope() as session:
            workflows = SqlWorkflowRepository(session)
            workflow = await workflows.get(workflow_id)
            if workflow is None or workflow.status not in ACTIVE_WORKFLOW_STATUSES:
                return
            projects = SqlProjectRepository(session)
            project = await projects.get(workflow.project_id)
            if project is None:
                return

            if WorkflowTimeoutPolicy.expired(workflow.deadline_at):
                await self._pause_locked(
                    session, workflow, project,
                    f"Workflow exceeded its {self.settings.workflow_timeout_minutes}-minute "
                    "time limit.",
                )
                return

            dag = WorkflowDAG.from_dict(workflow.dag)
            tasks_repo = SqlTaskRepository(session)
            all_tasks = await tasks_repo.list_for_workflow(workflow_id)
            latest = self._latest_by_node(all_tasks)

            all_satisfied = True
            for node in dag.nodes.values():
                if self._node_satisfied(node, latest, project.human_in_loop):
                    continue
                all_satisfied = False
                task = latest.get(node.key)
                if task is None or task.status != TaskStatus.PENDING:
                    continue
                deps_ready = all(
                    self._node_satisfied(dag.nodes[dep], latest, project.human_in_loop)
                    for dep in node.inputs
                )
                if deps_ready:
                    await tasks_repo.update_fields(
                        task.id, status=TaskStatus.QUEUED.value, queued_at=_utcnow()
                    )
                    to_enqueue.append(task.id)

            if all_satisfied:
                now = _utcnow()
                await workflows.update_fields(
                    workflow_id, status=WorkflowStatus.COMPLETED.value,
                    finished_at=now, current_stage="done",
                )
                await projects.update_status(project.id, ProjectStatus.COMPLETED)
                await SqlMessageRepository(session).add(
                    AgentMessage(
                        id=uuid.uuid4(),
                        project_id=project.id,
                        message_type=MessageType.SYSTEM,
                        content=f"“{project.name}” is complete and approved. "
                                "Artifacts are ready to download. 🎉",
                    )
                )
                await NotificationService(session, self.event_bus).notify(
                    project.owner_id,
                    NotificationType.WORKFLOW_COMPLETED,
                    f"“{project.name}” is ready",
                    "All agents finished and the CEO approved the delivery.",
                    project_id=project.id,
                )
                completed_project = project
            else:
                stage = self._current_stage(dag, latest, project.human_in_loop)
                if stage != workflow.current_stage:
                    await workflows.update_fields(workflow_id, current_stage=stage)

        if completed_project is not None:
            await self.event_bus.publish_project_event(
                completed_project.id, "workflow.updated",
                {"status": "completed", "current_stage": "done"},
            )
        for task_id in to_enqueue:
            await self.queue.enqueue_agent_task(task_id)

    def _current_stage(self, dag: WorkflowDAG, latest: dict[str, Task],
                       human_in_loop: bool) -> str:
        for stage in STAGE_ORDER:
            for node in dag.nodes.values():
                if node.stage == stage and not self._node_satisfied(
                    node, latest, human_in_loop
                ):
                    return stage
        return "done"

    # ----------------------------------------------------------- task runner

    async def run_agent_task(self, task_id: uuid.UUID) -> None:
        correlation_id = uuid.UUID(new_correlation_id())
        async with session_scope() as session:
            tasks_repo = SqlTaskRepository(session)
            task = await tasks_repo.get(task_id)
            if task is None:
                return
            workflow = await SqlWorkflowRepository(session).get(task.workflow_id)
            project = await SqlProjectRepository(session).get(task.project_id)
            if workflow is None or project is None:
                return
            if workflow.status not in ACTIVE_WORKFLOW_STATUSES:
                logger.info("task_skipped_inactive_workflow", task_id=str(task_id))
                return
            if not await tasks_repo.try_mark_running(task_id):
                return  # already claimed (idempotency under ARQ re-delivery)
            profile = None
            agents = SqlAgentRepository(session)
            for candidate in await agents.list_active():
                if candidate.id == task.agent_id:
                    profile = candidate
                    break
            if profile is None:
                await tasks_repo.update_fields(task_id, status=TaskStatus.FAILED.value,
                                               error="agent profile missing")
                return
            messages = SqlMessageRepository(session)
            await messages.add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=task.project_id,
                    task_id=task.id,
                    recipient_agent_id=profile.id,
                    correlation_id=correlation_id,
                    message_type=MessageType.ASSIGNMENT,
                    content=f"@{profile.name} — {task.title}"
                            + (f" (revision round {task.revision_round})"
                               if task.revision_round else ""),
                    payload={"node_key": task.node_key,
                             "revision_round": task.revision_round},
                )
            )
        await self._publish_task_update(task, TaskStatus.RUNNING, profile.key)
        await self._publish_message_event(task.project_id)

        started = _utcnow()
        try:
            output = await self._execute(task, profile, correlation_id)
        except BudgetExceededError as exc:
            await self._pause(task.workflow_id, str(exc.message))
            return
        except MalformedOutputError as exc:
            await self._handle_task_failure(task, profile, str(exc.message))
            return
        except Exception as exc:  # LLM errors, circuit open, unexpected
            await self._handle_task_failure(task, profile, str(exc)[:500])
            return

        AGENT_TASK_DURATION.labels(profile.key).observe(
            (_utcnow() - started).total_seconds()
        )
        await self._complete_task(task, profile, output, correlation_id)

    async def _execute(self, task: Task, profile, correlation_id: uuid.UUID) -> dict[str, Any]:
        async with session_scope() as session:
            project = await SqlProjectRepository(session).get(task.project_id)
            assert project is not None
            tasks_repo = SqlTaskRepository(session)
            all_tasks = await tasks_repo.list_for_workflow(task.workflow_id)
            latest = self._latest_by_node(all_tasks)
            workflow = await SqlWorkflowRepository(session).get(task.workflow_id)
            assert workflow is not None
            dag = WorkflowDAG.from_dict(workflow.dag)
            node = dag.nodes.get(task.node_key)
            upstream: dict[str, dict] = {}
            if node:
                for dep in node.inputs:
                    dep_task = latest.get(dep)
                    if dep_task and dep_task.output:
                        upstream[dep] = dep_task.output
            memory = MemoryService(session, self.gateway)
            memories = await memory.project_context(task.project_id)
            hits = await memory.semantic_recall(
                task.project_id, f"{task.title}\n{task.description}"
            )
            feedback = ""
            if task.revision_round > 0:
                feedback = (task.description.split("REVISION FEEDBACK:", 1)[-1]
                            if "REVISION FEEDBACK:" in task.description else "")

        inputs = PromptInputs(
            user_request=project.prompt,
            task_title=task.title,
            task_description=task.description,
            output_schema_key="",  # set by the agent from its config
            upstream_outputs=upstream,
            project_memories=memories,
            semantic_hits=hits,
            revision_feedback=feedback,
        )
        agent = build_agent(profile, self.gateway)
        return await agent.execute(task, inputs)

    # ----------------------------------------------------------- completion

    async def _complete_task(
        self, task: Task, profile, output: dict[str, Any], correlation_id: uuid.UUID
    ) -> None:
        is_gate_rejection = (
            output.get("verdict") == VerdictType.CHANGES_REQUESTED.value
        )
        async with session_scope() as session:
            tasks_repo = SqlTaskRepository(session)
            await tasks_repo.update_fields(
                task.id,
                status=TaskStatus.COMPLETED.value,
                output=output,
                finished_at=_utcnow(),
                error=None,
            )
            messages = SqlMessageRepository(session)
            await messages.add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=task.project_id,
                    task_id=task.id,
                    sender_agent_id=profile.id,
                    correlation_id=correlation_id,
                    message_type=MessageType.REVIEW if "verdict" in output
                    else MessageType.RESULT,
                    content=humanize_output(profile.key, output),
                    payload={"node_key": task.node_key, "output_keys": list(output.keys())},
                )
            )
            # Persist generated files as versioned artifacts.
            files = output.get("files") or []
            if files:
                artifact_service = ArtifactService(session, self.event_bus, self.queue)
                await artifact_service.save_files(
                    task.project_id,
                    [GeneratedFile(path=f["path"], content=f["content"],
                                   language=f.get("language", "text")) for f in files],
                    created_by_task_id=task.id,
                )
            # Tier-2 memory: record the agent's decisions.
            decisions = output.get("decisions") or []
            if decisions:
                await MemoryService(session, self.gateway).record_decisions(
                    task.project_id, decisions, source_task_id=task.id
                )
            # Structured verdicts become review rows.
            if "verdict" in output:
                await SqlReviewRepository(session).add(
                    Review(
                        id=uuid.uuid4(),
                        project_id=task.project_id,
                        task_id=task.id,
                        reviewer_agent_id=profile.id,
                        verdict=VerdictType(output["verdict"]),
                        reasons=output.get("reasons", []),
                        round=task.revision_round,
                    )
                )
            # Queue result text for tier-3 embedding.
            try:
                await self.queue.enqueue_embedding(
                    task.project_id, "conversation", task.id,
                    f"{task.title}\n{humanize_output(profile.key, output)}",
                )
            except Exception:
                logger.warning("embedding_enqueue_failed", exc_info=True)

        await self._publish_task_update(task, TaskStatus.COMPLETED, profile.key)
        await self._publish_message_event(task.project_id)

        if is_gate_rejection:
            await self._route_revisions(task, profile, output)
        else:
            await self._maybe_pause_for_human(task, output)
            await self._advance(task.workflow_id)

    async def _maybe_pause_for_human(self, task: Task, output: dict[str, Any]) -> None:
        """Human-in-the-loop: approved gates wait for the user before unblocking."""
        if "verdict" not in output or output.get("human_approved"):
            return
        async with session_scope() as session:
            project = await SqlProjectRepository(session).get(task.project_id)
            if project is None or not project.human_in_loop:
                return
            workflow = await SqlWorkflowRepository(session).get(task.workflow_id)
            if workflow is None or workflow.status not in ACTIVE_WORKFLOW_STATUSES:
                return
            await SqlWorkflowRepository(session).set_status(
                task.workflow_id, WorkflowStatus.REVIEW,
                paused_reason=f"Awaiting your approval at gate '{task.node_key}'.",
            )
            await SqlProjectRepository(session).update_status(
                task.project_id, ProjectStatus.REVIEW
            )
            await NotificationService(session, self.event_bus).notify(
                project.owner_id,
                NotificationType.APPROVAL_REQUIRED,
                f"Approval required: {project.name}",
                f"The {task.node_key.replace('_', ' ')} gate passed agent review and "
                "awaits your sign-off.",
                project_id=project.id,
            )
        await self.event_bus.publish_project_event(
            task.project_id, "workflow.updated",
            {"status": "review", "paused_reason": f"awaiting approval: {task.node_key}"},
        )

    # ------------------------------------------------------------- revisions

    async def _route_revisions(self, review_task: Task, reviewer, output: dict) -> None:
        policy = RevisionLoopPolicy(self.settings.max_revision_loops)
        if not policy.can_request_revision(review_task.revision_round):
            await self._pause(
                review_task.workflow_id,
                f"Revision loop limit reached at '{review_task.node_key}' "
                f"(round {review_task.revision_round}). The last verdict is attached to "
                "the review history.",
            )
            return

        reasons = output.get("reasons", [])
        targets: dict[str, list[dict]] = {}
        for reason in reasons:
            node = reason.get("target_node", "")
            if node in REVISABLE_NODES:
                targets.setdefault(node, []).append(reason)
        if not targets:
            # Reviewer rejected but named no valid node — treat as needing attention.
            await self._pause(
                review_task.workflow_id,
                f"'{review_task.node_key}' requested changes without a valid target node.",
            )
            return

        new_round = review_task.revision_round + 1
        async with session_scope() as session:
            tasks_repo = SqlTaskRepository(session)
            agents = SqlAgentRepository(session)
            messages = SqlMessageRepository(session)
            workflow = await SqlWorkflowRepository(session).get(review_task.workflow_id)
            assert workflow is not None
            dag = WorkflowDAG.from_dict(workflow.dag)
            all_tasks = await tasks_repo.list_for_workflow(review_task.workflow_id)
            latest = self._latest_by_node(all_tasks)

            for node_key, node_reasons in targets.items():
                node = dag.nodes.get(node_key)
                prev = latest.get(node_key)
                if node is None or prev is None:
                    continue
                target_profile = await agents.get_by_key(node.agent_key)
                if target_profile is None:
                    continue
                feedback = "\n".join(
                    f"- [{r.get('severity', 'medium')}] {r.get('description', '')} "
                    f"Suggestion: {r.get('suggestion', '')}"
                    for r in node_reasons
                )
                target_round = prev.revision_round + 1
                await tasks_repo.add(
                    Task(
                        id=uuid.uuid4(),
                        project_id=review_task.project_id,
                        workflow_id=review_task.workflow_id,
                        agent_id=target_profile.id,
                        node_key=node_key,
                        title=f"{node.title} (revision {target_round})",
                        description=f"{node.instructions}\n\nREVISION FEEDBACK:\n{feedback}",
                        status=TaskStatus.PENDING,
                        revision_round=target_round,
                    )
                )
                await messages.add(
                    AgentMessage(
                        id=uuid.uuid4(),
                        project_id=review_task.project_id,
                        task_id=review_task.id,
                        sender_agent_id=reviewer.id,
                        recipient_agent_id=target_profile.id,
                        message_type=MessageType.REVISION_REQUEST,
                        content=f"@{target_profile.name} — changes requested "
                                f"(round {target_round}):\n{feedback}",
                        payload={"target_node": node_key, "round": target_round},
                    )
                )
            # Re-run the review gate after the revisions land.
            await tasks_repo.add(
                Task(
                    id=uuid.uuid4(),
                    project_id=review_task.project_id,
                    workflow_id=review_task.workflow_id,
                    agent_id=review_task.agent_id,
                    node_key=review_task.node_key,
                    title=f"{review_task.title.split(' (round')[0]} (round {new_round})",
                    description=review_task.description.split("\n\nREVISION FEEDBACK:")[0],
                    status=TaskStatus.PENDING,
                    revision_round=new_round,
                )
            )
        await self._publish_message_event(review_task.project_id)
        await self._advance(review_task.workflow_id)

    # ---------------------------------------------------------------- errors

    async def _handle_task_failure(self, task: Task, profile, error: str) -> None:
        retry_policy = TaskRetryPolicy(self.settings.max_task_retries)
        new_attempt = task.attempt + 1
        async with session_scope() as session:
            tasks_repo = SqlTaskRepository(session)
            if retry_policy.can_retry(new_attempt):
                await tasks_repo.update_fields(
                    task.id, status=TaskStatus.QUEUED.value, attempt=new_attempt, error=error
                )
                retrying = True
            else:
                await tasks_repo.update_fields(
                    task.id, status=TaskStatus.DEAD_LETTER.value, attempt=new_attempt,
                    error=error, finished_at=_utcnow(),
                )
                retrying = False
            await SqlMessageRepository(session).add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=task.project_id,
                    task_id=task.id,
                    sender_agent_id=profile.id,
                    message_type=MessageType.STATUS,
                    content=(f"Task '{task.title}' failed (attempt {new_attempt}): {error}. "
                             + ("Retrying…" if retrying else "Moved to dead-letter queue.")),
                )
            )
        await self._publish_message_event(task.project_id)
        if retrying:
            await self._publish_task_update(task, TaskStatus.QUEUED, profile.key)
            await self.queue.enqueue_agent_task(task.id)
        else:
            await self._publish_task_update(task, TaskStatus.DEAD_LETTER, profile.key)
            await self._pause(
                task.workflow_id,
                f"Task '{task.title}' failed {new_attempt} times and was dead-lettered: "
                f"{error}",
            )

    async def _pause(self, workflow_id: uuid.UUID, reason: str) -> None:
        async with session_scope() as session:
            workflow = await SqlWorkflowRepository(session).get(workflow_id)
            if workflow is None or workflow.status not in ACTIVE_WORKFLOW_STATUSES:
                return
            project = await SqlProjectRepository(session).get(workflow.project_id)
            if project is None:
                return
            await self._pause_locked(session, workflow, project, reason)
        await self.event_bus.publish_project_event(
            workflow.project_id, "workflow.updated",
            {"status": "needs_attention", "paused_reason": reason},
        )

    async def _pause_locked(self, session, workflow: Workflow, project: Project,
                            reason: str) -> None:
        await SqlWorkflowRepository(session).set_status(
            workflow.id, WorkflowStatus.NEEDS_ATTENTION, paused_reason=reason
        )
        await SqlProjectRepository(session).update_status(
            project.id, ProjectStatus.NEEDS_ATTENTION
        )
        await SqlMessageRepository(session).add(
            AgentMessage(
                id=uuid.uuid4(),
                project_id=project.id,
                message_type=MessageType.SYSTEM,
                content=f"Workflow paused — needs your attention: {reason}",
            )
        )
        await NotificationService(session, self.event_bus).notify(
            project.owner_id,
            NotificationType.NEEDS_ATTENTION,
            f"“{project.name}” needs attention",
            reason,
            project_id=project.id,
        )
        logger.warning("workflow_paused", workflow_id=str(workflow.id), reason=reason)

    # ------------------------------------------------------------ user actions

    async def resume_workflow(self, project_id: uuid.UUID) -> None:
        """Resume from NEEDS_ATTENTION: requeue dead-letter tasks and continue."""
        async with session_scope() as session:
            workflows = SqlWorkflowRepository(session)
            workflow = await workflows.get_by_project(project_id)
            if workflow is None or workflow.status != WorkflowStatus.NEEDS_ATTENTION:
                return
            await workflows.set_status(workflow.id, WorkflowStatus.IN_PROGRESS, None)
            await SqlProjectRepository(session).update_status(
                project_id, ProjectStatus.IN_PROGRESS
            )
            tasks_repo = SqlTaskRepository(session)
            for task in await tasks_repo.list_for_workflow(workflow.id):
                if task.status == TaskStatus.DEAD_LETTER:
                    await tasks_repo.update_fields(
                        task.id, status=TaskStatus.QUEUED.value, attempt=0, error=None
                    )
                    await self.queue.enqueue_agent_task(task.id)
        await self.event_bus.publish_project_event(
            project_id, "workflow.updated", {"status": "in_progress"}
        )
        await self._advance(workflow.id)

    async def apply_human_approval(
        self, project_id: uuid.UUID, gate: str, approved: bool, feedback: str = ""
    ) -> None:
        async with session_scope() as session:
            workflows = SqlWorkflowRepository(session)
            workflow = await workflows.get_by_project(project_id)
            if workflow is None:
                return
            tasks_repo = SqlTaskRepository(session)
            all_tasks = await tasks_repo.list_for_workflow(workflow.id)
            latest = self._latest_by_node(all_tasks)
            gate_task = latest.get(gate)
            if gate_task is None or gate_task.output is None:
                return
            if approved:
                output = {**gate_task.output, "human_approved": True}
                await tasks_repo.update_fields(gate_task.id, output=output)
            await workflows.set_status(workflow.id, WorkflowStatus.IN_PROGRESS, None)
            await SqlProjectRepository(session).update_status(
                project_id, ProjectStatus.IN_PROGRESS
            )
            await SqlMessageRepository(session).add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    task_id=gate_task.id,
                    message_type=MessageType.SYSTEM,
                    content=(f"Owner approved the '{gate}' gate."
                             if approved else
                             f"Owner requested changes at the '{gate}' gate: {feedback}"),
                )
            )
        await self._publish_message_event(project_id)
        if approved:
            await self._advance(workflow.id)
        else:
            # Human rejection re-runs the gate with the feedback injected.
            fake_output = {
                "verdict": VerdictType.CHANGES_REQUESTED.value,
                "summary": feedback or "Owner requested changes.",
                "reasons": [
                    {"severity": "high", "area": "owner-feedback",
                     "target_node": "backend_impl", "description": feedback or
                     "Owner requested changes.", "suggestion": ""}
                ],
            }
            async with session_scope() as session:
                profile = None
                for candidate in await SqlAgentRepository(session).list_active():
                    if candidate.id == gate_task.agent_id:
                        profile = candidate
                        break
            if profile is not None:
                await self._route_revisions(gate_task, profile, fake_output)

    async def cancel_workflow(self, project_id: uuid.UUID) -> None:
        async with session_scope() as session:
            workflows = SqlWorkflowRepository(session)
            workflow = await workflows.get_by_project(project_id)
            project = await SqlProjectRepository(session).get(project_id)
            if workflow is None or project is None:
                return
            if workflow.status in (WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED):
                return
            await workflows.update_fields(
                workflow.id, status=WorkflowStatus.CANCELLED.value, finished_at=_utcnow()
            )
            await SqlProjectRepository(session).update_status(
                project_id, ProjectStatus.CANCELLED
            )
            await SqlMessageRepository(session).add(
                AgentMessage(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    message_type=MessageType.SYSTEM,
                    content="Project cancelled by the owner. All pending work stopped.",
                )
            )
        await self.event_bus.publish_project_event(
            project_id, "workflow.updated", {"status": "cancelled"}
        )

    # ---------------------------------------------------------------- events

    async def _publish_task_update(self, task: Task, status: TaskStatus,
                                   agent_key: str) -> None:
        await self.event_bus.publish_project_event(
            task.project_id,
            "task.updated",
            {
                "task_id": str(task.id),
                "node_key": task.node_key,
                "status": status.value,
                "agent_key": agent_key,
                "revision_round": task.revision_round,
            },
        )

    async def _publish_message_event(self, project_id: uuid.UUID) -> None:
        """Nudge clients to refetch messages (full rows also flow via agent.message)."""
        await self.event_bus.publish_project_event(project_id, "messages.changed", {})


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
