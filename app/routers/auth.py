from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    _utcnow_naive,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(user: User, db: AsyncSession) -> TokenResponse:
    access_token = create_access_token(user.id)
    raw_refresh = generate_refresh_token()
    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=_utcnow_naive() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_token)
    await db.commit()
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    await db.flush()
    return await _issue_tokens(user, db)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return await _issue_tokens(user, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if stored is None or stored.revoked or stored.expires_at < _utcnow_naive():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=body.refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout")
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)) -> dict:
    stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(body.refresh_token)))
    if stored is not None:
        stored.revoked = True
        await db.commit()
    return {"detail": "Logged out"}
