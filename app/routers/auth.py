import logging
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email import send_password_reset_email, send_otp_email
from app.core.rate_limit import limiter
from app.core.security import (
    _utcnow_naive,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    hash_token,
    verify_password,
)
from app.database import get_db
from app.models.email_otp import EmailOTP
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)

logger = logging.getLogger(__name__)

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


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    await db.flush()

    otp = f"{secrets.randbelow(1000000):06d}"
    email_otp = EmailOTP(
        user_id=user.id,
        otp_hash=hash_token(otp),
        expires_at=_utcnow_naive() + timedelta(minutes=10),
    )
    db.add(email_otp)
    await db.commit()

    try:
        await send_otp_email(user.email, otp)
    except Exception:
        logger.exception("Failed to send verification email to user %s", user.id)

    return {"detail": "Registration successful. Please check your email for a verification code."}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )
    return await _issue_tokens(user, db)


@router.post("/verify-email", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_email(request: Request, body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    email_otp = await db.scalar(
        select(EmailOTP)
        .where(
            EmailOTP.user_id == user.id,
            EmailOTP.used == False,
            EmailOTP.expires_at > _utcnow_naive(),
        )
        .order_by(EmailOTP.expires_at.desc())
    )

    if email_otp is None or email_otp.otp_hash != hash_token(body.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user.is_verified = True
    email_otp.used = True
    await db.commit()

    return await _issue_tokens(user, db)


@router.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(request: Request, body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is not None and not user.is_verified:
        await db.execute(
            update(EmailOTP)
            .where(EmailOTP.user_id == user.id, EmailOTP.used == False)
            .values(used=True)
        )

        otp = f"{secrets.randbelow(1000000):06d}"
        email_otp = EmailOTP(
            user_id=user.id,
            otp_hash=hash_token(otp),
            expires_at=_utcnow_naive() + timedelta(minutes=10),
        )
        db.add(email_otp)
        await db.commit()

        try:
            await send_otp_email(user.email, otp)
        except Exception:
            logger.exception("Failed to send verification email to user %s", user.id)

    return {"detail": "If that email exists and is unverified, a new code has been sent."}


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


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is not None:
        raw_token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=_utcnow_naive() + timedelta(minutes=30),
        )
        db.add(reset_token)
        await db.commit()
        reset_url = f"{settings.FRONTEND_RESET_URL}?token={raw_token}"
        try:
            await send_password_reset_email(user.email, reset_url)
        except Exception:
            logger.exception("Failed to send password reset email to user %s", user.id)
    return {"detail": "If that email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    reset_token = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token))
    )
    if reset_token is None or reset_token.used or reset_token.expires_at < _utcnow_naive():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    user.password_hash = hash_password(body.new_password)
    reset_token.used = True
    await db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    await db.commit()
    return {"detail": "Password reset successfully"}
