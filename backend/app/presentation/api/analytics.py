"""Company-wide analytics."""
from fastapi import APIRouter

from app.application.services.analytics_service import AnalyticsService
from app.domain.value_objects import UserRole
from app.presentation.deps import CurrentUser, DbSession

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(session: DbSession, user: CurrentUser):
    owner_id = None if user.role == UserRole.ADMIN else user.id
    return await AnalyticsService(session).overview(owner_id)
