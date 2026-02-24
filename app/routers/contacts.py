from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.contact import Contact
from app.schemas.contact import (
    ContactResponse,
    ContactDetailResponse,
    ContactCreateRequest,
    ContactUpdateRequest,
    ContactListResponse,
)

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    tag: Optional[str] = None,
    source: Optional[str] = None,
    favorites_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List contacts with pagination, search, and filters."""
    query = select(Contact).where(Contact.user_id == user.id)
    count_query = select(func.count(Contact.id)).where(Contact.user_id == user.id)

    # Search by name, email, company
    if search:
        from sqlalchemy import Text
        search_filter = or_(
            Contact.display_name.ilike(f"%{search}%"),
            Contact.first_name.ilike(f"%{search}%"),
            Contact.last_name.ilike(f"%{search}%"),
            Contact.company.ilike(f"%{search}%"),
            Contact.emails.cast(Text).ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if tag:
        tag_filter = Contact.tags.contains([tag])
        query = query.where(tag_filter)
        count_query = count_query.where(tag_filter)

    if source:
        query = query.where(Contact.source == source)
        count_query = count_query.where(Contact.source == source)

    if favorites_only:
        query = query.where(Contact.is_favorite == True)
        count_query = count_query.where(Contact.is_favorite == True)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(Contact.display_name.asc().nullslast()).offset(offset).limit(per_page)

    result = await db.execute(query)
    contacts = result.scalars().all()

    return ContactListResponse(
        contacts=[_to_response(c) for c in contacts],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{contact_id}", response_model=ContactDetailResponse)
async def get_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single contact with full details."""
    contact = await _get_contact_or_404(db, user.id, contact_id)
    return _to_detail_response(contact)


@router.post("", response_model=ContactDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    request: ContactCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new contact."""
    contact = Contact(
        user_id=user.id,
        first_name=request.first_name,
        middle_name=request.middle_name,
        last_name=request.last_name,
        display_name=request.display_name or _build_display_name(request.first_name, request.last_name),
        headline=request.headline,
        company=request.company,
        job_title=request.job_title,
        department=request.department,
        emails=[e.model_dump() for e in request.emails],
        phones=[p.model_dump() for p in request.phones],
        addresses=[a.model_dump() for a in request.addresses],
        social_profiles=[s.model_dump() for s in request.social_profiles],
        websites=request.websites,
        tags=request.tags,
        location=request.location,
        birthday=request.birthday,
        notes=request.notes,
        source="manual",
        is_favorite=request.is_favorite,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return _to_detail_response(contact)


@router.put("/{contact_id}", response_model=ContactDetailResponse)
async def update_contact(
    contact_id: str,
    request: ContactUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a contact."""
    contact = await _get_contact_or_404(db, user.id, contact_id)

    contact.first_name = request.first_name
    contact.middle_name = request.middle_name
    contact.last_name = request.last_name
    contact.display_name = request.display_name or _build_display_name(request.first_name, request.last_name)
    contact.headline = request.headline
    contact.company = request.company
    contact.job_title = request.job_title
    contact.department = request.department
    contact.emails = [e.model_dump() for e in request.emails]
    contact.phones = [p.model_dump() for p in request.phones]
    contact.addresses = [a.model_dump() for a in request.addresses]
    contact.social_profiles = [s.model_dump() for s in request.social_profiles]
    contact.websites = request.websites
    contact.tags = request.tags
    contact.location = request.location
    contact.birthday = request.birthday
    contact.notes = request.notes
    contact.is_favorite = request.is_favorite

    await db.commit()
    await db.refresh(contact)
    return _to_detail_response(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contact."""
    contact = await _get_contact_or_404(db, user.id, contact_id)
    await db.delete(contact)
    await db.commit()


@router.patch("/{contact_id}/favorite")
async def toggle_favorite(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle favorite status on a contact."""
    contact = await _get_contact_or_404(db, user.id, contact_id)
    contact.is_favorite = not contact.is_favorite
    await db.commit()
    return {"is_favorite": contact.is_favorite}


# --- Helpers ---

async def _get_contact_or_404(db: AsyncSession, user_id, contact_id: str) -> Contact:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


def _build_display_name(first: str | None, last: str | None) -> str:
    parts = [p for p in [first, last] if p]
    return " ".join(parts) or "Unknown"


def _to_response(c: Contact) -> ContactResponse:
    return ContactResponse(
        id=str(c.id),
        display_name=c.display_name,
        first_name=c.first_name,
        last_name=c.last_name,
        company=c.company,
        job_title=c.job_title,
        emails=c.emails or [],
        phones=c.phones or [],
        tags=c.tags or [],
        location=c.location,
        avatar_url=c.avatar_url,
        is_favorite=c.is_favorite,
        source=c.source,
        last_interaction_at=c.last_interaction_at,
        created_at=c.created_at,
    )


def _to_detail_response(c: Contact) -> ContactDetailResponse:
    return ContactDetailResponse(
        id=str(c.id),
        display_name=c.display_name,
        first_name=c.first_name,
        middle_name=c.middle_name,
        last_name=c.last_name,
        headline=c.headline,
        company=c.company,
        job_title=c.job_title,
        department=c.department,
        custom_role=c.custom_role,
        emails=c.emails or [],
        phones=c.phones or [],
        addresses=c.addresses or [],
        social_profiles=c.social_profiles or [],
        websites=c.websites or [],
        tags=c.tags or [],
        location=c.location,
        location_country=c.location_country,
        birthday=c.birthday,
        gender=c.gender,
        segment=c.segment,
        stage=c.stage,
        score=c.score,
        notes=c.notes,
        avatar_url=c.avatar_url,
        is_favorite=c.is_favorite,
        source=c.source,
        first_interaction_at=c.first_interaction_at,
        first_interaction_type=c.first_interaction_type,
        last_interaction_at=c.last_interaction_at,
        last_interaction_type=c.last_interaction_type,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )
