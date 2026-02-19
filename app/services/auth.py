import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User, RefreshToken


def create_access_token(user_id: str) -> tuple[str, datetime]:
    """Create a short-lived JWT access token. Returns (token, expires_at)."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "type": "access",
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def create_refresh_token_value() -> str:
    """Generate a unique refresh token string."""
    return str(uuid.uuid4())


async def store_refresh_token(db: AsyncSession, user_id: uuid.UUID, token: str) -> RefreshToken:
    """Store a refresh token in the database."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    refresh = RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at,
    )
    db.add(refresh)
    await db.commit()
    return refresh


async def validate_refresh_token(db: AsyncSession, token: str) -> Optional[RefreshToken]:
    """Validate a refresh token. Returns the token record if valid, None otherwise."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token: str) -> None:
    """Revoke a refresh token."""
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    refresh = result.scalar_one_or_none()
    if refresh:
        refresh.revoked = True
        await db.commit()


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Revoke all refresh tokens for a user (logout everywhere)."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    tokens = result.scalars().all()
    for t in tokens:
        t.revoked = True
    await db.commit()


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate an access token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


async def get_or_create_user(db: AsyncSession, email: str, display_name: str = None, avatar_url: str = None) -> User:
    """Get existing user by email or create a new one."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        # Update profile info from Google if changed
        if display_name and user.display_name != display_name:
            user.display_name = display_name
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
        await db.commit()
        return user

    user = User(
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
