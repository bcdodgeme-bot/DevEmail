from pydantic_settings import BaseSettings
from typing import List, Optional
import json


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Redis (optional — not currently used)
    REDIS_URL: Optional[str] = None

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Credential encryption (Fernet key for IMAP/SMTP passwords at rest)
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    CREDENTIAL_ENCRYPTION_KEY: Optional[str] = None

    # Cookie security — set to False for local HTTP development
    COOKIE_SECURE: bool = True

    # Google OAuth (optional — app boots without these, OAuth just won't work)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "https://devemail.damnitcarl.dev/api/auth/google/callback"

    # Syntax Prime integration (AI draft-reply assistant)
    SYNTAX_URL: Optional[str] = None

    # App
    APP_NAME: str = "Unified Inbox"
    APP_URL: str = "https://devemail.damnitcarl.dev"
    CORS_ORIGINS: str = '["https://devemail.damnitcarl.dev","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
