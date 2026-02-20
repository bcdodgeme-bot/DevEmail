from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.services.imap_sync import sync_account

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/{account_id}")
async def trigger_sync(
    account_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an IMAP sync for a specific account."""
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.sync_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sync is disabled for this account",
        )

    summary = await sync_account(account, user.id, db)

    if "error" in summary:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=summary["error"],
        )

    return {
        "status": "ok",
        "account": account.email_address,
        "fetched": summary["fetched"],
        "new": summary["new"],
        "skipped": summary["skipped"],
    }


@router.post("")
async def trigger_sync_all(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger IMAP sync for ALL accounts belonging to the current user."""
    result = await db.execute(
        select(Account).where(
            Account.user_id == user.id,
            Account.sync_enabled == True,
        )
    )
    accounts = result.scalars().all()

    if not accounts:
        return {"status": "ok", "message": "No sync-enabled accounts found", "results": []}

    results = []
    for account in accounts:
        summary = await sync_account(account, user.id, db)
        results.append({
            "account": account.email_address,
            **summary,
        })

    return {"status": "ok", "results": results}
