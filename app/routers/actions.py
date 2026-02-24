"""
Actions Router

POST /messages/{message_id}/unsubscribe  — one-click unsubscribe
POST /contacts/score                      — bulk contact scoring
POST /contacts/{contact_id}/score         — single contact scoring
POST /contacts/enrich                     — bulk contact enrichment
POST /contacts/{contact_id}/enrich        — single contact enrichment
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.contact import Contact
from app.models.message import Message
from app.models.unsubscribe import UnsubscribeLink

router = APIRouter(tags=["actions"])


# --- Unsubscribe ---

@router.post("/messages/{message_id}/unsubscribe")
async def execute_unsubscribe(
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute one-click unsubscribe for a message."""
    result = await db.execute(
        select(UnsubscribeLink).where(UnsubscribeLink.message_id == message_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="No unsubscribe link found")

    if link.executed:
        return {"status": "already_executed", "executed_at": link.executed_at}

    from app.services.unsubscribe_service import UnsubscribeService
    service = UnsubscribeService()
    try:
        result = await service.execute(link)
        link.executed = True
        from datetime import datetime, timezone
        link.executed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "success", "method": result.get("method", "unknown")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unsubscribe failed: {str(e)}")


# --- Contact Scoring ---

@router.post("/contacts/score")
async def score_all_contacts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recalculate scores for all contacts."""
    from app.services.contact_scoring import ContactScoringService
    service = ContactScoringService(db)
    result = await service.score_all(user.id)
    return result


@router.post("/contacts/{contact_id}/score")
async def score_single_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recalculate score for a single contact."""
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    from app.services.contact_scoring import ContactScoringService
    service = ContactScoringService(db)
    score_data = await service.score_contact(contact)
    return score_data


# --- Contact Enrichment ---

@router.post("/contacts/enrich")
async def enrich_all_contacts(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enrich unenriched contacts with public data."""
    from app.services.contact_enrichment import ContactEnrichmentService
    service = ContactEnrichmentService(db)
    try:
        result = await service.enrich_batch(user.id, limit=limit)
        return result
    finally:
        await service.close()


@router.post("/contacts/{contact_id}/enrich")
async def enrich_single_contact(
    contact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enrich a single contact with public data."""
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    from app.services.contact_enrichment import ContactEnrichmentService
    service = ContactEnrichmentService(db)
    try:
        data = await service.enrich_contact(contact)
        return {"status": "enriched" if data else "no_data", "fields": list(data.keys())}
    finally:
        await service.close()
