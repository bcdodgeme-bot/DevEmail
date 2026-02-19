from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List


class ContactEmail(BaseModel):
    type: str
    address: str


class ContactPhone(BaseModel):
    type: str
    number: str


class ContactAddress(BaseModel):
    type: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class ContactSocial(BaseModel):
    platform: str
    url: str


class ContactResponse(BaseModel):
    id: str
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    emails: List[ContactEmail] = []
    phones: List[ContactPhone] = []
    tags: List[str] = []
    location: Optional[str] = None
    avatar_url: Optional[str] = None
    is_favorite: bool = False
    source: str
    last_interaction_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContactDetailResponse(ContactResponse):
    middle_name: Optional[str] = None
    headline: Optional[str] = None
    department: Optional[str] = None
    custom_role: Optional[str] = None
    addresses: List[ContactAddress] = []
    social_profiles: List[ContactSocial] = []
    websites: List[str] = []
    location_country: Optional[str] = None
    birthday: Optional[date] = None
    gender: Optional[str] = None
    segment: Optional[str] = None
    stage: Optional[str] = None
    score: int = 0
    notes: Optional[str] = None
    first_interaction_at: Optional[datetime] = None
    first_interaction_type: Optional[str] = None
    last_interaction_type: Optional[str] = None
    updated_at: datetime


class ContactCreateRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    emails: List[ContactEmail] = []
    phones: List[ContactPhone] = []
    addresses: List[ContactAddress] = []
    social_profiles: List[ContactSocial] = []
    websites: List[str] = []
    tags: List[str] = []
    location: Optional[str] = None
    birthday: Optional[date] = None
    notes: Optional[str] = None
    is_favorite: bool = False


class ContactUpdateRequest(ContactCreateRequest):
    pass


class ContactListResponse(BaseModel):
    contacts: List[ContactResponse]
    total: int
    page: int
    per_page: int
