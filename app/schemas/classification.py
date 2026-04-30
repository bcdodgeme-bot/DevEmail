from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


Category = Literal["people", "bulk"]


# --- Per-category counts ---

class CategoryCountSlot(BaseModel):
    unread: int
    total: int


class CategoryCountsResponse(BaseModel):
    all: CategoryCountSlot
    people: CategoryCountSlot
    bulk: CategoryCountSlot


# --- Manual move (POST /api/messages/{id}/category) ---

class CategoryUpdateRequest(BaseModel):
    category: Category
    apply_to_domain: bool = False
    apply_to_existing: bool = False


class CategoryUpdateResponse(BaseModel):
    id: str
    category: Category
    category_source: str
    # How many other messages had their category overridden by the
    # apply_to_existing flag. 0 if apply_to_existing was false.
    applied_to_existing_count: int = 0


# --- Sender classifications CRUD ---

class SenderClassificationResponse(BaseModel):
    id: str
    account_id: str
    sender_address: str
    sender_domain: Optional[str] = None
    is_domain_rule: bool
    category: Category
    learned_from: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SenderClassificationListResponse(BaseModel):
    items: List[SenderClassificationResponse]
    total: int
    page: int
    per_page: int


class SenderClassificationUpdateRequest(BaseModel):
    category: Category
