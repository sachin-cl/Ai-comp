"""WebSocket endpoint: JWT auth on connect, per-project subscriptions, Redis pub/sub
fan-out so any API replica can serve any client."""
import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.errors import UnauthorizedError
from app.core.logging import get_logger
from app.core.metrics import WS_CONNECTIONS
from app.core.security import decode_access_token
from app.domain.value_objects import UserRole
from app.infrastructure.db.engine import session_scope
from app.infrastructure.db.repositories import SqlProjectRepository, SqlUserRepository
from app.infrastructure.redis.client import get_redis
from app.infrastructure.redis.event_bus import project_channel, user_channel

logger = get_logger("ws")
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")) -> None:
    # --- authenticate before accepting ---
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        role = payload.get("role", "member")
    except (UnauthorizedError, ValueError, KeyError):
        await ws.close(code=4401, reason="invalid token")
        return
    async with session_scope() as session:
        user = await SqlUserRepository(session).get(user_id)
    if user is None or not user.is_active:
        await ws.close(code=4401, reason="unknown user")
        return

    await ws.accept()
    WS_CONNECTIONS.inc()
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(user_channel(user_id))
    subscribed: set[str] = set()

    async def forward_events() -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                await ws.send_text(message["data"])
            except Exception:
                return

    forwarder = asyncio.create_task(forward_events())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                command = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "code": "BAD_MESSAGE"})
                continue
            action = command.get("action")
            project_id = str(command.get("project_id", ""))
            if action == "subscribe" and project_id:
                if await _can_access(user_id, role, project_id):
                    await pubsub.subscribe(project_channel(project_id))
                    subscribed.add(project_id)
                    await ws.send_json({"type": "subscribed", "project_id": project_id})
                else:
                    await ws.send_json({"type": "error", "code": "FORBIDDEN",
                                        "project_id": project_id})
            elif action == "unsubscribe" and project_id in subscribed:
                await pubsub.unsubscribe(project_channel(project_id))
                subscribed.discard(project_id)
                await ws.send_json({"type": "unsubscribed", "project_id": project_id})
            elif action == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await ws.send_json({"type": "error", "code": "UNKNOWN_ACTION"})
    except WebSocketDisconnect:
        pass
    finally:
        WS_CONNECTIONS.dec()
        forwarder.cancel()
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:
            pass


async def _can_access(user_id: uuid.UUID, role: str, project_id: str) -> bool:
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        return False
    async with session_scope() as session:
        project = await SqlProjectRepository(session).get(pid)
    if project is None:
        return False
    return role == UserRole.ADMIN.value or project.owner_id == user_id
