"""User notifications."""
import uuid

from fastapi import APIRouter, Query, status

from app.infrastructure.db.repositories import SqlNotificationRepository
from app.presentation.deps import CurrentUser, DbSession
from app.presentation.schemas.common import Page
from app.presentation.schemas.projects import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationResponse])
async def list_notifications(
    session: DbSession,
    user: CurrentUser,
    unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[NotificationResponse]:
    items, total = await SqlNotificationRepository(session).list_for_user(
        user.id, unread, limit, offset
    )
    return Page(
        items=[
            NotificationResponse(
                id=n.id, project_id=n.project_id, type=n.type.value, title=n.title,
                body=n.body, read_at=n.read_at, created_at=n.created_at,
            )
            for n in items
        ],
        total=total, limit=limit, offset=offset,
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: uuid.UUID, session: DbSession, user: CurrentUser) -> None:
    await SqlNotificationRepository(session).mark_read(user.id, notification_id)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(session: DbSession, user: CurrentUser) -> None:
    await SqlNotificationRepository(session).mark_read(user.id, None)
