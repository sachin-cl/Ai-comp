"""Auth endpoints (rate-limited)."""
from fastapi import APIRouter, Request, status

from app.application.services.auth_service import AuthService
from app.core.config import get_settings
from app.infrastructure.redis.rate_limiter import enforce_rate_limit
from app.presentation.deps import CurrentUser, DbSession, client_ip
from app.presentation.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    await enforce_rate_limit(
        f"auth:{client_ip(request)}", settings.auth_rate_limit, settings.auth_rate_window
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, body: RegisterRequest, session: DbSession) -> UserResponse:
    await _auth_rate_limit(request)
    user = await AuthService(session).register(body.email, body.password, body.full_name)
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name,
                        role=user.role.value)


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, session: DbSession) -> TokenResponse:
    await _auth_rate_limit(request)
    pair = await AuthService(session).login(body.email, body.password)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, body: RefreshRequest, session: DbSession) -> TokenResponse:
    await _auth_rate_limit(request)
    pair = await AuthService(session).refresh(body.refresh_token)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: DbSession, user: CurrentUser) -> None:
    await AuthService(session).logout(body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name,
                        role=user.role.value)
