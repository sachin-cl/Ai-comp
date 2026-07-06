"""Redis pub/sub event bus for real-time fan-out to WebSocket clients."""
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.domain.ports.event_bus import EventBus
from app.infrastructure.redis.client import get_redis


def project_channel(project_id: uuid.UUID | str) -> str:
    return f"events:{project_id}"


def user_channel(user_id: uuid.UUID | str) -> str:
    return f"events:user:{user_id}"


class RedisEventBus(EventBus):
    async def _publish(self, channel: str, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "ts": datetime.now(UTC).isoformat(),
            **payload,
        }
        await get_redis().publish(channel, json.dumps(event, default=str))

    async def publish_project_event(
        self, project_id: uuid.UUID, event_type: str, payload: dict[str, Any]
    ) -> None:
        await self._publish(
            project_channel(project_id), event_type, {"project_id": str(project_id), **payload}
        )

    async def publish_user_event(
        self, user_id: uuid.UUID, event_type: str, payload: dict[str, Any]
    ) -> None:
        await self._publish(user_channel(user_id), event_type, payload)

    async def subscribe(self, channels: list[str]) -> AsyncIterator[dict[str, Any]]:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(*channels)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    yield json.loads(message["data"])
                except json.JSONDecodeError:
                    continue
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()


_bus: RedisEventBus | None = None


def get_event_bus() -> RedisEventBus:
    global _bus
    if _bus is None:
        _bus = RedisEventBus()
    return _bus
