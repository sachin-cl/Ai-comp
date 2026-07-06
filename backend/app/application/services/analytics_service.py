"""Agent performance and company-wide analytics."""
import uuid
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import models as m


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def agent_stats(self, agent_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Per-agent: tasks completed, revision rate, avg tokens, avg latency."""
        task_q = (
            select(
                m.TaskModel.agent_id,
                func.count(m.TaskModel.id).label("tasks_total"),
                func.sum(
                    case((m.TaskModel.status == "completed", 1), else_=0)
                ).label("tasks_completed"),
                func.sum(
                    case((m.TaskModel.revision_round > 0, 1), else_=0)
                ).label("revision_tasks"),
            )
            .group_by(m.TaskModel.agent_id)
        )
        llm_q = (
            select(
                m.LLMCallModel.agent_id,
                func.coalesce(
                    func.avg(m.LLMCallModel.prompt_tokens + m.LLMCallModel.completion_tokens),
                    0,
                ).label("avg_tokens"),
                func.coalesce(func.avg(m.LLMCallModel.latency_ms), 0).label("avg_latency_ms"),
                func.coalesce(func.sum(m.LLMCallModel.cost_usd), 0).label("cost_usd"),
                func.count(m.LLMCallModel.id).label("llm_calls"),
            )
            .where(m.LLMCallModel.agent_id.is_not(None))
            .group_by(m.LLMCallModel.agent_id)
        )
        if agent_id is not None:
            task_q = task_q.where(m.TaskModel.agent_id == agent_id)
            llm_q = llm_q.where(m.LLMCallModel.agent_id == agent_id)

        tasks = {r.agent_id: r for r in (await self.session.execute(task_q)).all()}
        llm = {r.agent_id: r for r in (await self.session.execute(llm_q)).all()}
        agents = (await self.session.execute(select(m.AgentModel))).scalars().all()

        stats = []
        for agent in agents:
            if agent_id is not None and agent.id != agent_id:
                continue
            t = tasks.get(agent.id)
            calls = llm.get(agent.id)
            tasks_total = int(t.tasks_total) if t else 0
            stats.append(
                {
                    "agent_key": agent.key,
                    "name": agent.name,
                    "role_title": agent.role_title,
                    "tasks_completed": int(t.tasks_completed or 0) if t else 0,
                    "tasks_total": tasks_total,
                    "revision_rate": round(
                        (int(t.revision_tasks or 0) / tasks_total), 3
                    ) if t and tasks_total else 0.0,
                    "avg_tokens": round(float(calls.avg_tokens), 1) if calls else 0.0,
                    "avg_latency_ms": round(float(calls.avg_latency_ms), 1) if calls else 0.0,
                    "cost_usd": round(float(calls.cost_usd), 4) if calls else 0.0,
                    "llm_calls": int(calls.llm_calls) if calls else 0,
                }
            )
        return stats

    async def overview(self, owner_id: uuid.UUID | None) -> dict[str, Any]:
        project_q = select(m.ProjectModel.status, func.count(m.ProjectModel.id)).group_by(
            m.ProjectModel.status
        )
        totals_q = select(
            func.coalesce(func.sum(m.ProjectModel.tokens_used), 0),
            func.coalesce(func.sum(m.ProjectModel.cost_usd), 0),
        )
        if owner_id is not None:
            project_q = project_q.where(m.ProjectModel.owner_id == owner_id)
            totals_q = totals_q.where(m.ProjectModel.owner_id == owner_id)
        by_status = {row[0]: int(row[1]) for row in (await self.session.execute(project_q))}
        tokens, cost = (await self.session.execute(totals_q)).one()
        return {
            "projects_by_status": by_status,
            "total_tokens": int(tokens),
            "total_cost_usd": float(cost),
            "agents": await self.agent_stats(),
        }
