"""Event bus port — pub/sub for real-time fan-out."""
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class EventBus(ABC):
    @abstractmethod
    async def publish_project_event(
        self, project_id: uuid.UUID, event_type: str, payload: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def publish_user_event(
        self, user_id: uuid.UUID, event_type: str, payload: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def subscribe(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield events published on the given channels."""
        ...
