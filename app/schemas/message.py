from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# --- Addresses ---

class EmailAddress(BaseModel):
    address: str
    name: Optional[str] = None


# --- Attachments ---

class AttachmentResponse(BaseModel):
    id: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None

    class Config:
        from_attributes = True


# --- Messages ---

class MessageResponse(BaseModel):
    id: str
    thread_id: str
    account_id: str
    folder_id: Optional[str] = None
    from_address: Optional[str] = None
    from_name: Optional[str] = None
    to_addresses: List[EmailAddress] = []
    cc_addresses: List[EmailAddress] = []
    subject: Optional[str] = None
    snippet: Optional[str] = None
    is_read: bool
    is_starred: bool
    is_draft: bool
    is_sent: bool
    has_attachments: bool
    received_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageDetailResponse(MessageResponse):
    bcc_addresses: List[EmailAddress] = []
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    message_id_header: Optional[str] = None
    in_reply_to: Optional[str] = None
    is_archived: bool
    is_trashed: bool
    read_receipt_requested: bool
    read_receipt_sent_at: Optional[datetime] = None
    attachments: List[AttachmentResponse] = []
    created_at: datetime


# --- Threads ---

class ThreadResponse(BaseModel):
    id: str
    subject: Optional[str] = None
    last_message_at: Optional[datetime] = None
    message_count: int
    is_starred: bool
    is_snoozed: bool
    snoozed_until: Optional[datetime] = None
    # Preview info from latest message
    latest_from_name: Optional[str] = None
    latest_from_address: Optional[str] = None
    latest_snippet: Optional[str] = None
    has_unread: bool = False
    account_ids: List[str] = []

    class Config:
        from_attributes = True


class ThreadDetailResponse(ThreadResponse):
    messages: List[MessageDetailResponse] = []
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    threads: List[ThreadResponse]
    total: int
    page: int
    per_page: int


# --- Compose / Send ---

class ComposeRequest(BaseModel):
    account_id: str
    to_addresses: List[EmailAddress]
    cc_addresses: List[EmailAddress] = []
    bcc_addresses: List[EmailAddress] = []
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    in_reply_to_message_id: Optional[str] = None
    signature_id: Optional[str] = None
    read_receipt_requested: bool = False
    is_draft: bool = False


class DraftUpdateRequest(BaseModel):
    to_addresses: Optional[List[EmailAddress]] = None
    cc_addresses: Optional[List[EmailAddress]] = None
    bcc_addresses: Optional[List[EmailAddress]] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    signature_id: Optional[str] = None


# --- Bulk Actions ---

class BulkActionRequest(BaseModel):
    message_ids: List[str]


class SnoozeRequest(BaseModel):
    thread_id: str
    snoozed_until: datetime


# --- Search ---

class MessageSearchRequest(BaseModel):
    query: str
    account_id: Optional[str] = None
    folder_id: Optional[str] = None
    is_read: Optional[bool] = None
    has_attachments: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    per_page: int = 50
