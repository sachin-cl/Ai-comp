"""Agent roster + per-agent performance stats."""

from fastapi import APIRouter

from app.application.services.analytics_service import AnalyticsService
from app.core.errors import NotFoundError
from app.infrastructure.db.repositories import SqlAgentRepository
from app.presentation.deps import CurrentUser, DbSession
from app.presentation.schemas.projects import AgentResponse

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(session: DbSession, user: CurrentUser) -> list[AgentResponse]:
    agents = await SqlAgentRepository(session).list_active()
    return [
        AgentResponse(
            key=a.key, name=a.name, role_title=a.role_title, personality=a.personality,
            provider=a.provider, model=a.model, is_active=a.is_active,
        )
        for a in agents
    ]


@router.get("/{key}/stats")
async def agent_stats(key: str, session: DbSession, user: CurrentUser):
    agent = await SqlAgentRepository(session).get_by_key(key)
    if agent is None:
        raise NotFoundError(f"Agent '{key}' not found")
    stats = await AnalyticsService(session).agent_stats(agent.id)
    return stats[0] if stats else {
        "agent_key": key, "tasks_completed": 0, "tasks_total": 0,
        "revision_rate": 0.0, "avg_tokens": 0.0, "avg_latency_ms": 0.0,
        "cost_usd": 0.0, "llm_calls": 0,
    }
