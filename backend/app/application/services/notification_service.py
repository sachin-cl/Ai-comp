"""User notifications: persist + real-time push over the user's event channel."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Notification
from app.domain.ports.event_bus import EventBus
from app.domain.value_objects import NotificationType
from app.infrastructure.db.repositories import SqlNotificationRepository


class NotificationService:
    def __init__(self, session: AsyncSession, event_bus: EventBus) -> None:
        self.repo = SqlNotificationRepository(session)
        self.event_bus = event_bus

    async def notify(
        self,
        user_id: uuid.UUID,
        type_: NotificationType,
        title: str,
        body: str = "",
        project_id: uuid.UUID | None = None,
    ) -> Notification:
        notification = await self.repo.add(
            Notification(
                id=uuid.uuid4(),
                user_id=user_id,
                type=type_,
                title=title,
                body=body,
                project_id=project_id,
            )
        )
        await self.event_bus.publish_user_event(
            user_id,
            "notification",
            {
                "id": str(notification.id),
                "notification_type": type_.value,
                "title": title,
                "body": body,
                "project_id": str(project_id) if project_id else None,
                "created_at": notification.created_at.isoformat()
                if notification.created_at
                else None,
            },
        )
        return notification
