from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# --- Signatures ---

class SignatureCreate(BaseModel):
    name: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    is_default: bool = False


class SignatureUpdate(SignatureCreate):
    pass


class SignatureResponse(BaseModel):
    id: str
    account_id: str
    name: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Accounts ---

class AccountCreateGmail(BaseModel):
    """Used after Google OAuth callback links a Gmail account."""
    # Gmail accounts are created automatically during OAuth callback.
    # This schema is for manually linking additional Gmail accounts.
    pass


class AccountCreateStalwart(BaseModel):
    """Link a Stalwart mail server account."""
    email_address: str
    display_name: Optional[str] = None
    imap_host: str = "mail.damnitcarl.dev"
    imap_port: int = 993
    smtp_host: str = "mail.damnitcarl.dev"
    smtp_port: int = 465
    username: str
    password: str


class AccountUpdate(BaseModel):
    display_name: Optional[str] = None
    is_default: Optional[bool] = None
    sync_enabled: Optional[bool] = None


class AccountResponse(BaseModel):
    id: str
    provider: str
    email_address: str
    display_name: Optional[str] = None
    auth_type: str
    is_default: bool
    sync_enabled: bool
    last_synced_at: Optional[datetime] = None
    signatures: List[SignatureResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class AccountListResponse(BaseModel):
    accounts: List[AccountResponse]
    total: int
