import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.schemas.auth import (
    TokenResponse,
    RefreshRequest,
    UserResponse,
    LoginRequest,
    RegisterRequest,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token_value,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    authenticate_user,
    create_local_user,
    get_or_create_user,
    create_oauth_state,
    verify_oauth_state,
)
from app.services.google_oauth import (
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_info,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly auth cookies on the response."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")


# ===========================================
# Local Auth (email + password)
# ===========================================

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(max_requests=5, window_seconds=300)),
):
    """Create a new user account with email and password."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Create the user
    user = await create_local_user(
        db,
        email=request.email,
        password=request.password,
        display_name=request.display_name,
    )

    # Issue tokens
    access_token, expires_at = create_access_token(str(user.id))
    refresh_token = create_refresh_token_value()
    await store_refresh_token(db, user.id, refresh_token)

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(max_requests=10, window_seconds=300)),
):
    """Authenticate with email and password."""
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Issue tokens
    access_token, expires_at = create_access_token(str(user.id))
    refresh_token = create_refresh_token_value()
    await store_refresh_token(db, user.id, refresh_token)

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


# ===========================================
# Google OAuth (link Gmail account)
# Requires existing auth — this ADDS a Gmail
# account, it doesn't create a user.
# ===========================================

@router.get("/google/login")
async def google_login(
    user: User = Depends(get_current_user),
):
    """
    Return the Google OAuth consent URL as JSON.
    Requires auth — the frontend calls this with the JWT,
    then redirects the browser to the returned URL.
    """
    state = create_oauth_state(str(user.id))
    url = get_google_auth_url(state=state)
    return {"auth_url": url}


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.
    Links the Gmail account to the user identified by the state parameter.
    """
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter",
        )

    # Verify the signed state token and extract user_id
    user_id = verify_oauth_state(state)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        logger.error("Failed to exchange Google authorization code: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to complete Google authentication. Please try again.",
        )

    google_access_token = token_data.get("access_token")
    google_refresh_token = token_data.get("refresh_token")

    try:
        user_info = await get_google_user_info(google_access_token)
    except Exception as e:
        logger.error("Failed to fetch Google user info: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to retrieve Google account information. Please try again.",
        )

    gmail_email = user_info.get("email")
    gmail_name = user_info.get("name")
    gmail_avatar = user_info.get("picture")

    # Update user avatar from Google if they don't have one
    if not user.avatar_url and gmail_avatar:
        user.avatar_url = gmail_avatar

    # Create or update the linked Gmail account
    result = await db.execute(
        select(Account).where(
            Account.user_id == user.id,
            Account.provider == "gmail",
            Account.email_address == gmail_email,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.oauth_token = google_access_token
        if google_refresh_token:
            account.oauth_refresh_token = google_refresh_token
        account.display_name = gmail_name
    else:
        # Check if this is the user's first account (make it default)
        count_result = await db.execute(
            select(Account).where(Account.user_id == user.id)
        )
        existing_count = len(count_result.scalars().all())

        account = Account(
            user_id=user.id,
            provider="gmail",
            email_address=gmail_email,
            display_name=gmail_name,
            auth_type="oauth",
            oauth_token=google_access_token,
            oauth_refresh_token=google_refresh_token,
            is_default=existing_count == 0,
            sync_enabled=True,
        )
        db.add(account)

    await db.commit()

    # Redirect back to the frontend settings/accounts page
    return RedirectResponse(url="/settings?account_linked=true")


# ===========================================
# Token management
# ===========================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    http_request: Request,
    response: Response,
    body: RefreshRequest = None,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit(max_requests=30, window_seconds=300)),
):
    """Exchange a refresh token for a new access token + refresh token (rotation).
    Accepts token from httpOnly cookie or request body."""
    # Prefer cookie, fall back to body
    token = http_request.cookies.get("refresh_token") or (body.refresh_token if body else None)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    existing = await validate_refresh_token(db, token)
    if not existing:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    await revoke_refresh_token(db, token)

    access_token, expires_at = create_access_token(str(existing.user_id))
    new_refresh_token = create_refresh_token_value()
    await store_refresh_token(db, existing.user_id, new_refresh_token)

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
    )


@router.post("/logout")
async def logout(
    http_request: Request,
    response: Response,
    body: RefreshRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current refresh token and clear auth cookies."""
    token = http_request.cookies.get("refresh_token") or (body.refresh_token if body else None)
    if token:
        await revoke_refresh_token(db, token)
    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all refresh tokens for the current user."""
    await revoke_all_user_tokens(db, user.id)
    _clear_auth_cookies(response)
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
