from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.schemas.auth import TokenResponse, RefreshRequest, UserResponse
from app.services.auth import (
    create_access_token,
    create_refresh_token_value,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_or_create_user,
)
from app.services.google_oauth import (
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_info,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google/login")
async def google_login():
    """Redirect user to Google OAuth consent screen."""
    url = get_google_auth_url()
    return RedirectResponse(url=url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback. Creates/updates user and linked Gmail account."""
    try:
        # Exchange code for tokens
        token_data = exchange_code_for_tokens(code)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange authorization code: {str(e)}",
        )

    google_access_token = token_data.get("access_token")
    google_refresh_token = token_data.get("refresh_token")

    # Get user info from Google
    try:
        user_info = await get_google_user_info(google_access_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch user info: {str(e)}",
        )

    email = user_info.get("email")
    display_name = user_info.get("name")
    avatar_url = user_info.get("picture")

    # Get or create user
    user = await get_or_create_user(db, email, display_name, avatar_url)

    # Create or update the linked Gmail account
    result = await db.execute(
        select(Account).where(
            Account.user_id == user.id,
            Account.provider == "gmail",
            Account.email_address == email,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.oauth_token = google_access_token
        if google_refresh_token:
            account.oauth_refresh_token = google_refresh_token
    else:
        account = Account(
            user_id=user.id,
            provider="gmail",
            email_address=email,
            display_name=display_name,
            auth_type="oauth",
            oauth_token=google_access_token,
            oauth_refresh_token=google_refresh_token,
            is_default=True,
            sync_enabled=True,
        )
        db.add(account)

    await db.commit()

    # Create app tokens
    access_token, expires_at = create_access_token(str(user.id))
    refresh_token = create_refresh_token_value()
    await store_refresh_token(db, user.id, refresh_token)

    # TODO: In production, redirect to frontend with tokens
    # For now, return JSON
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a refresh token for a new access token + refresh token (rotation)."""
    # Validate the refresh token
    existing = await validate_refresh_token(db, request.refresh_token)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Revoke old refresh token (rotation)
    await revoke_refresh_token(db, request.refresh_token)

    # Issue new tokens
    access_token, expires_at = create_access_token(str(existing.user_id))
    new_refresh_token = create_refresh_token_value()
    await store_refresh_token(db, existing.user_id, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
    )


@router.post("/logout")
async def logout(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific refresh token."""
    await revoke_refresh_token(db, request.refresh_token)
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all refresh tokens for the current user."""
    await revoke_all_user_tokens(db, user.id)
    return {"message": "All sessions revoked"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get the current authenticated user."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        timezone=user.timezone,
        created_at=user.created_at,
    )
