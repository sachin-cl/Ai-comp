"""FastAPI dependencies: DB session, current user, role guards."""
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.domain.entities import User
from app.domain.value_objects import UserRole
from app.infrastructure.db.engine import get_session_factory
from app.infrastructure.db.repositories import SqlUserRepository

bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_access_token(credentials.credentials)
    user = await SqlUserRepository(session).get(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User no longer exists or is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin role required")
    return user


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
