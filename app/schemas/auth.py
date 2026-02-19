from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


# --- Auth Requests ---

class LoginRequest(BaseModel):
    """Email + password login."""
    email: str
    password: str


class RegisterRequest(BaseModel):
    """Create a new local account."""
    email: str
    password: str
    display_name: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


# --- Auth Responses ---

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: str = "America/New_York"
    created_at: datetime

    class Config:
        from_attributes = True
