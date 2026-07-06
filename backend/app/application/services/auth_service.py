"""Auth: register, login, refresh-token rotation, logout."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import EmailTakenError, InvalidCredentialsError, InvalidRefreshTokenError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.domain.entities import User
from app.domain.value_objects import UserRole
from app.infrastructure.db.repositories import SqlUserRepository


class TokenPair:
    def __init__(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = SqlUserRepository(session)

    async def register(self, email: str, password: str, full_name: str) -> User:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            raise EmailTakenError("An account with this email already exists")
        user = User(
            id=uuid.uuid4(),
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.MEMBER,
        )
        try:
            return await self.users.add(user)
        except IntegrityError as exc:  # concurrent duplicate registration
            raise EmailTakenError("An account with this email already exists") from exc

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(
            password, user.password_hash
        ):
            raise InvalidCredentialsError("Invalid email or password")
        return await self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_hash = hash_refresh_token(refresh_token)
        user = await self.users.get_refresh_token_user(token_hash)
        if user is None:
            raise InvalidRefreshTokenError("Refresh token is invalid, expired, or revoked")
        await self.users.revoke_refresh_token(token_hash)  # rotation
        return await self._issue_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        await self.users.revoke_refresh_token(hash_refresh_token(refresh_token))

    async def _issue_tokens(self, user: User) -> TokenPair:
        settings = get_settings()
        access_token, expires_in = create_access_token(user.id, user.role.value)
        refresh_token = generate_refresh_token()
        await self.users.save_refresh_token(
            user.id,
            hash_refresh_token(refresh_token),
            datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
        return TokenPair(access_token, refresh_token, expires_in)
