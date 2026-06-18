from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.models.signature import Signature
from app.services.crypto import encrypt_credential
from app.schemas.account import (
    AccountCreateStalwart,
    AccountUpdate,
    AccountResponse,
    AccountListResponse,
    SignatureCreate,
    SignatureUpdate,
    SignatureResponse,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


# --- Accounts ---

@router.get("", response_model=AccountListResponse)
async def list_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all linked email accounts for the current user."""
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user.id)
        .order_by(Account.is_default.desc(), Account.created_at)
    )
    accounts = result.scalars().all()
    return AccountListResponse(
        accounts=[_to_account_response(a) for a in accounts],
        total=len(accounts),
    )


@router.post("/stalwart", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def link_stalwart_account(
    request: AccountCreateStalwart,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Link a Stalwart mail server account."""
    # Check for duplicate
    result = await db.execute(
        select(Account).where(
            Account.user_id == user.id,
            Account.email_address == request.email_address,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address is already linked",
        )

    # If no other accounts, make this the default
    count_result = await db.execute(
        select(Account).where(Account.user_id == user.id)
    )
    existing_count = len(count_result.scalars().all())

    account = Account(
        user_id=user.id,
        provider="stalwart",
        email_address=request.email_address,
        display_name=request.display_name,
        auth_type="credentials",
        imap_host=request.imap_host,
        imap_port=request.imap_port,
        smtp_host=request.smtp_host,
        smtp_port=request.smtp_port,
        username=request.username,
        password=encrypt_credential(request.password),
        is_default=existing_count == 0,
        sync_enabled=True,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return _to_account_response(account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific linked account."""
    account = await _get_account_or_404(db, user.id, account_id)
    return _to_account_response(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    request: AccountUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update account settings (display name, default, sync)."""
    account = await _get_account_or_404(db, user.id, account_id)

    if request.display_name is not None:
        account.display_name = request.display_name

    if request.sync_enabled is not None:
        account.sync_enabled = request.sync_enabled

    if request.is_default is True:
        # Atomically clear all defaults for this user, then set the new one
        await db.execute(
            update(Account)
            .where(Account.user_id == user.id)
            .values(is_default=False)
        )
        account.is_default = True

    await db.commit()
    await db.refresh(account)
    return _to_account_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_account(
    account_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink an email account.

    Deletes the account row (so we don't retain IMAP credentials) but KEEPS
    the messages synced from it: messages.account_id is ON DELETE SET NULL, so
    those messages are orphaned and stay visible in the inbox.
    """
    account = await _get_account_or_404(db, user.id, account_id)

    # The Account.signatures relationship is eagerly loaded (lazy="selectin")
    # with no passive_deletes, so deleting the account makes SQLAlchemy nullify
    # the loaded signature rows. Null out account_id explicitly first (and keep
    # the session in sync) so that succeeds against the SET NULL FK instead of
    # tripping the old NOT NULL constraint.
    await db.execute(
        update(Signature)
        .where(Signature.account_id == account.id)
        .values(account_id=None)
    )
    await db.delete(account)
    await db.commit()


# --- Signatures ---

@router.get("/{account_id}/signatures", response_model=list[SignatureResponse])
async def list_signatures(
    account_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all signatures for an account."""
    account = await _get_account_or_404(db, user.id, account_id)
    result = await db.execute(
        select(Signature).where(Signature.account_id == account.id)
    )
    return [_to_signature_response(s) for s in result.scalars().all()]


@router.post("/{account_id}/signatures", response_model=SignatureResponse, status_code=status.HTTP_201_CREATED)
async def create_signature(
    account_id: str,
    request: SignatureCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new signature for an account."""
    account = await _get_account_or_404(db, user.id, account_id)

    # If setting as default, unset others
    if request.is_default:
        result = await db.execute(
            select(Signature).where(
                Signature.account_id == account.id,
                Signature.is_default == True,
            )
        )
        for other in result.scalars().all():
            other.is_default = False

    signature = Signature(
        account_id=account.id,
        name=request.name,
        body_html=request.body_html,
        body_text=request.body_text,
        is_default=request.is_default,
    )
    db.add(signature)
    await db.commit()
    await db.refresh(signature)
    return _to_signature_response(signature)


@router.put("/{account_id}/signatures/{signature_id}", response_model=SignatureResponse)
async def update_signature(
    account_id: str,
    signature_id: str,
    request: SignatureUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a signature."""
    account = await _get_account_or_404(db, user.id, account_id)
    signature = await _get_signature_or_404(db, account.id, signature_id)

    if request.is_default:
        result = await db.execute(
            select(Signature).where(
                Signature.account_id == account.id,
                Signature.is_default == True,
                Signature.id != signature.id,
            )
        )
        for other in result.scalars().all():
            other.is_default = False

    signature.name = request.name
    signature.body_html = request.body_html
    signature.body_text = request.body_text
    signature.is_default = request.is_default

    await db.commit()
    await db.refresh(signature)
    return _to_signature_response(signature)


@router.delete("/{account_id}/signatures/{signature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signature(
    account_id: str,
    signature_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a signature."""
    account = await _get_account_or_404(db, user.id, account_id)
    signature = await _get_signature_or_404(db, account.id, signature_id)
    await db.delete(signature)
    await db.commit()


# --- Helpers ---

async def _get_account_or_404(db, user_id, account_id: str) -> Account:
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


async def _get_signature_or_404(db, account_id, signature_id: str) -> Signature:
    result = await db.execute(
        select(Signature).where(Signature.id == signature_id, Signature.account_id == account_id)
    )
    signature = result.scalar_one_or_none()
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signature not found")
    return signature


def _to_account_response(a: Account) -> AccountResponse:
    return AccountResponse(
        id=str(a.id),
        provider=a.provider,
        email_address=a.email_address,
        display_name=a.display_name,
        auth_type=a.auth_type,
        is_default=a.is_default,
        sync_enabled=a.sync_enabled,
        last_synced_at=a.last_synced_at,
        signatures=[_to_signature_response(s) for s in (a.signatures or [])],
        created_at=a.created_at,
    )


def _to_signature_response(s: Signature) -> SignatureResponse:
    return SignatureResponse(
        id=str(s.id),
        account_id=str(s.account_id),
        name=s.name,
        body_html=s.body_html,
        body_text=s.body_text,
        is_default=s.is_default,
        created_at=s.created_at,
    )
