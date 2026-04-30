"""
Sender classification rules — CRUD endpoints.

Future Settings UI will use these to view/edit per-account classification
overrides. Built now so the frontend can integrate later as a pure-
frontend addition.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.account import Account
from app.models.user import User
from app.models.sender_classification import SenderClassification
from app.schemas.classification import (
    SenderClassificationListResponse,
    SenderClassificationResponse,
    SenderClassificationUpdateRequest,
)

router = APIRouter(prefix="/sender-classifications", tags=["classifications"])


def _to_response(rule: SenderClassification) -> SenderClassificationResponse:
    return SenderClassificationResponse(
        id=str(rule.id),
        account_id=str(rule.account_id),
        sender_address=rule.sender_address,
        sender_domain=rule.sender_domain,
        is_domain_rule=rule.is_domain_rule,
        category=rule.category,  # type: ignore[arg-type]
        learned_from=rule.learned_from,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _get_rule_or_404(
    db: AsyncSession, user_id, rule_id: str,
) -> SenderClassification:
    """Fetch a rule scoped to the user's accounts. 404 otherwise."""
    user_accounts = select(Account.id).where(Account.user_id == user_id)
    result = await db.execute(
        select(SenderClassification).where(
            SenderClassification.id == rule_id,
            SenderClassification.account_id.in_(user_accounts),
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sender classification not found.",
        )
    return rule


@router.get("", response_model=SenderClassificationListResponse)
async def list_classifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    account_id: Optional[str] = None,
    category: Optional[str] = Query(None, pattern="^(people|bulk)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List classification rules. Scoped to the user's accounts."""
    user_accounts = select(Account.id).where(Account.user_id == user.id)
    where = SenderClassification.account_id.in_(user_accounts)
    if account_id:
        where = and_(where, SenderClassification.account_id == account_id)
    if category:
        where = and_(where, SenderClassification.category == category)

    total = (
        await db.execute(select(func.count(SenderClassification.id)).where(where))
    ).scalar() or 0

    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            select(SenderClassification)
            .where(where)
            .order_by(SenderClassification.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
    ).scalars().all()

    return SenderClassificationListResponse(
        items=[_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{rule_id}", response_model=SenderClassificationResponse)
async def get_classification(
    rule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = await _get_rule_or_404(db, user.id, rule_id)
    return _to_response(rule)


@router.patch("/{rule_id}", response_model=SenderClassificationResponse)
async def update_classification(
    rule_id: str,
    request: SenderClassificationUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a rule's category. learned_from is unchanged — we don't track
    edits as a new learning event for v1."""
    rule = await _get_rule_or_404(db, user.id, rule_id)
    rule.category = request.category
    await db.commit()
    return _to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification(
    rule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hard-delete a rule. Note: this does NOT revert previously-classified
    messages — they keep their category_source='override' and current
    category until the user manually moves them again.
    """
    rule = await _get_rule_or_404(db, user.id, rule_id)
    await db.delete(rule)
    await db.commit()
