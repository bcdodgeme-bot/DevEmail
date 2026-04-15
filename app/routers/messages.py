import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select, func, or_, and_, desc, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.models.thread import Thread
from app.models.message import Message
from app.models.attachment import Attachment
from app.schemas.message import (
    ThreadResponse,
    ThreadDetailResponse,
    ThreadListResponse,
    MessageDetailResponse,
    ComposeRequest,
    DraftUpdateRequest,
    BulkActionRequest,
    SnoozeRequest,
    MessageSearchRequest,
    AttachmentResponse,
    EmailAddress,
)

router = APIRouter(prefix="/messages", tags=["messages"])


# --- Inbox / Thread List ---

@router.get("/inbox", response_model=ThreadListResponse)
async def get_inbox(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=2000),
    account_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    starred_only: bool = False,
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the unified inbox as threaded conversations."""
    # Base query: threads belonging to user
    query = select(Thread).where(Thread.user_id == user.id)
    count_query = select(func.count(Thread.id)).where(Thread.user_id == user.id)

    if starred_only:
        query = query.where(Thread.is_starred == True)
        count_query = count_query.where(Thread.is_starred == True)

    # Filter by account: only threads that have messages from this account
    if account_id:
        account_filter = Thread.id.in_(
            select(Message.thread_id).where(Message.account_id == account_id)
        )
        query = query.where(account_filter)
        count_query = count_query.where(account_filter)

    # Filter by folder
    if folder_id:
        folder_filter = Thread.id.in_(
            select(Message.thread_id).where(Message.folder_id == folder_id)
        )
        query = query.where(folder_filter)
        count_query = count_query.where(folder_filter)

    # Filter unread: threads that contain at least one unread message
    if unread_only:
        unread_filter = Thread.id.in_(
            select(Message.thread_id).where(Message.is_read == False)
        )
        query = query.where(unread_filter)
        count_query = count_query.where(unread_filter)

    # Exclude threads where ALL messages are trashed
    active_msg_filter = Thread.id.in_(
        select(Message.thread_id).where(
            Message.is_trashed == False,
            Message.is_archived == False,
        )
    )
    query = query.where(active_msg_filter)
    count_query = count_query.where(active_msg_filter)

    # Exclude snoozed threads (unless snoozed_until has passed)
    query = query.where(
        or_(
            Thread.is_snoozed == False,
            Thread.snoozed_until <= func.now(),
        )
    )

    # Get total
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate, newest first
    offset = (page - 1) * per_page
    query = (
        query
        .options(selectinload(Thread.messages).selectinload(Message.account))
        .order_by(Thread.last_message_at.desc().nullslast())
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(query)
    threads = result.scalars().unique().all()

    return ThreadListResponse(
        threads=[_to_thread_response(t) for t in threads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/drafts", response_model=ThreadListResponse)
async def get_drafts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all draft messages."""
    draft_thread_ids = select(Message.thread_id).where(
        Message.is_draft == True,
        Message.account_id.in_(
            select(Account.id).where(Account.user_id == user.id)
        ),
    )

    query = (
        select(Thread)
        .where(Thread.id.in_(draft_thread_ids))
        .options(selectinload(Thread.messages))
        .order_by(Thread.updated_at.desc())
    )
    count_query = select(func.count(Thread.id)).where(Thread.id.in_(draft_thread_ids))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    threads = result.scalars().unique().all()

    return ThreadListResponse(
        threads=[_to_thread_response(t) for t in threads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/sent", response_model=ThreadListResponse)
async def get_sent(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all sent messages."""
    sent_thread_ids = select(Message.thread_id).where(
        Message.is_sent == True,
        Message.account_id.in_(
            select(Account.id).where(Account.user_id == user.id)
        ),
    )

    query = (
        select(Thread)
        .where(Thread.id.in_(sent_thread_ids))
        .options(selectinload(Thread.messages))
        .order_by(Thread.last_message_at.desc())
    )
    count_query = select(func.count(Thread.id)).where(Thread.id.in_(sent_thread_ids))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    threads = result.scalars().unique().all()

    return ThreadListResponse(
        threads=[_to_thread_response(t) for t in threads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/trash", response_model=ThreadListResponse)
async def get_trash(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trashed messages."""
    trash_thread_ids = select(Message.thread_id).where(
        Message.is_trashed == True,
        Message.account_id.in_(
            select(Account.id).where(Account.user_id == user.id)
        ),
    )

    query = (
        select(Thread)
        .where(Thread.id.in_(trash_thread_ids))
        .options(selectinload(Thread.messages))
        .order_by(Thread.updated_at.desc())
    )
    count_query = select(func.count(Thread.id)).where(Thread.id.in_(trash_thread_ids))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    threads = result.scalars().unique().all()

    return ThreadListResponse(
        threads=[_to_thread_response(t) for t in threads],
        total=total,
        page=page,
        per_page=per_page,
    )


# --- Single Thread ---

@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a full thread with all messages."""
    result = await db.execute(
        select(Thread)
        .where(Thread.id == thread_id, Thread.user_id == user.id)
        .options(
            selectinload(Thread.messages)
            .selectinload(Message.attachments),
            selectinload(Thread.messages)
            .selectinload(Message.unsubscribe_links),
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return _to_thread_detail_response(thread)


# --- Thread Actions ---

@router.patch("/threads/{thread_id}/star")
async def toggle_thread_star(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle star on a thread."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    thread.is_starred = not thread.is_starred
    await db.commit()
    return {"is_starred": thread.is_starred}


@router.patch("/threads/{thread_id}/read")
async def mark_thread_read(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages in a thread as read."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    result = await db.execute(
        select(Message).where(
            Message.thread_id == thread.id,
            Message.is_read == False,
        )
    )
    for msg in result.scalars().all():
        msg.is_read = True
    await db.commit()
    return {"status": "ok"}


@router.patch("/threads/{thread_id}/unread")
async def mark_thread_unread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark latest message in thread as unread."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    result = await db.execute(
        select(Message)
        .where(Message.thread_id == thread.id)
        .order_by(Message.received_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if msg:
        msg.is_read = False
        await db.commit()
    return {"status": "ok"}


@router.patch("/threads/{thread_id}/archive")
async def archive_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive all messages in a thread locally + propagate to Gmail."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    result = await db.execute(
        select(Message).where(Message.thread_id == thread.id)
    )
    messages = list(result.scalars().all())
    for msg in messages:
        msg.is_archived = True
    await db.commit()

    await _propagate_label_change(
        db, user.id, messages,
        remove_labels=["INBOX"],
    )
    return {"status": "ok"}


@router.patch("/threads/{thread_id}/trash")
async def trash_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move all messages in a thread to trash locally + propagate to Gmail."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    result = await db.execute(
        select(Message).where(Message.thread_id == thread.id)
    )
    messages = list(result.scalars().all())
    for msg in messages:
        msg.is_trashed = True
    await db.commit()

    await _propagate_label_change(
        db, user.id, messages,
        add_labels=["TRASH"],
        remove_labels=["INBOX"],
    )
    return {"status": "ok"}


@router.post("/threads/{thread_id}/snooze")
async def snooze_thread(
    thread_id: str,
    request: SnoozeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Snooze a thread until a specified time."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    thread.is_snoozed = True
    thread.snoozed_until = request.snoozed_until
    await db.commit()
    return {"is_snoozed": True, "snoozed_until": thread.snoozed_until}


@router.patch("/threads/{thread_id}/unsnooze")
async def unsnooze_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unsnooze a thread."""
    thread = await _get_thread_or_404(db, user.id, thread_id)
    thread.is_snoozed = False
    thread.snoozed_until = None
    await db.commit()
    return {"is_snoozed": False}


# --- Single Message Actions ---

@router.get("/{message_id}", response_model=MessageDetailResponse)
async def get_message(
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single message with full detail."""
    msg = await _get_message_or_404(db, user.id, message_id)
    return _to_message_detail(msg)


@router.patch("/{message_id}/star")
async def toggle_message_star(
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle star on a single message."""
    msg = await _get_message_or_404(db, user.id, message_id)
    msg.is_starred = not msg.is_starred
    await db.commit()
    return {"is_starred": msg.is_starred}


@router.patch("/{message_id}/read")
async def mark_message_read(
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as read."""
    msg = await _get_message_or_404(db, user.id, message_id)
    msg.is_read = True
    await db.commit()
    return {"is_read": True}


# --- Attachment Download ---

@router.get("/{message_id}/attachments/{attachment_id}/download")
async def download_attachment(
    message_id: str,
    attachment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download attachment content. Supports Gmail API and local storage."""
    # Verify user owns the message
    msg = await _get_message_or_404(db, user.id, message_id)

    # Find the attachment
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.message_id == msg.id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    # Get the account to determine provider
    result = await db.execute(
        select(Account).where(Account.id == msg.account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Download content based on provider
    if account.provider == "gmail" and attachment.remote_id:
        from app.services.gmail_sync import GmailSyncService
        gmail = GmailSyncService(db, account)
        try:
            content = await gmail.fetch_attachment_content(attachment.remote_id)
        finally:
            await gmail._close()
    elif attachment.storage_path:
        import aiofiles
        try:
            async with aiofiles.open(attachment.storage_path, "rb") as f:
                content = await f.read()
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment file not found on disk",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment content not available",
        )

    safe_filename = re.sub(r'[^\w\s\-.]', '_', attachment.filename or 'attachment')
    safe_filename = safe_filename.replace('\n', '').replace('\r', '')
    from urllib.parse import quote
    encoded_filename = quote(safe_filename, safe='')

    return Response(
        content=content,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded_filename}",
        },
    )

@router.post("/bulk/read")
async def bulk_mark_read(
    request: BulkActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark multiple messages as read."""
    messages = await _get_user_messages(db, user.id, request.message_ids)
    for msg in messages:
        msg.is_read = True
    await db.commit()
    return {"updated": len(messages)}


@router.post("/bulk/unread")
async def bulk_mark_unread(
    request: BulkActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark multiple messages as unread."""
    messages = await _get_user_messages(db, user.id, request.message_ids)
    for msg in messages:
        msg.is_read = False
    await db.commit()
    return {"updated": len(messages)}


@router.post("/bulk/archive")
async def bulk_archive(
    request: BulkActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive multiple messages."""
    messages = await _get_user_messages(db, user.id, request.message_ids)
    for msg in messages:
        msg.is_archived = True
    await db.commit()
    return {"updated": len(messages)}


@router.post("/bulk/trash")
async def bulk_trash(
    request: BulkActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trash multiple messages."""
    messages = await _get_user_messages(db, user.id, request.message_ids)
    for msg in messages:
        msg.is_trashed = True
    await db.commit()
    return {"updated": len(messages)}


# --- Search ---

@router.post("/search", response_model=ThreadListResponse)
async def search_messages(
    request: MessageSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across messages."""
    # Find matching message IDs using full text search
    msg_query = (
        select(Message.thread_id)
        .where(
            Message.account_id.in_(
                select(Account.id).where(Account.user_id == user.id)
            )
        )
    )

    # Full text search
    search_vector = func.to_tsvector(
        'english',
        func.coalesce(Message.subject, '') + ' ' +
        func.coalesce(Message.body_text, '') + ' ' +
        func.coalesce(Message.from_name, '') + ' ' +
        func.coalesce(Message.from_address, '')
    )
    search_query = func.plainto_tsquery('english', request.query)
    msg_query = msg_query.where(search_vector.op('@@')(search_query))

    # Additional filters
    if request.account_id:
        msg_query = msg_query.where(Message.account_id == request.account_id)
    if request.folder_id:
        msg_query = msg_query.where(Message.folder_id == request.folder_id)
    if request.is_read is not None:
        msg_query = msg_query.where(Message.is_read == request.is_read)
    if request.has_attachments is not None:
        msg_query = msg_query.where(Message.has_attachments == request.has_attachments)
    if request.date_from:
        msg_query = msg_query.where(Message.received_at >= request.date_from)
    if request.date_to:
        msg_query = msg_query.where(Message.received_at <= request.date_to)

    matching_thread_ids = msg_query.distinct()

    # Count
    count_query = select(func.count()).select_from(
        select(Thread.id).where(Thread.id.in_(matching_thread_ids)).subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Fetch threads
    offset = (request.page - 1) * request.per_page
    thread_query = (
        select(Thread)
        .where(Thread.id.in_(matching_thread_ids))
        .options(selectinload(Thread.messages))
        .order_by(Thread.last_message_at.desc())
        .offset(offset)
        .limit(request.per_page)
    )

    result = await db.execute(thread_query)
    threads = result.scalars().unique().all()

    return ThreadListResponse(
        threads=[_to_thread_response(t) for t in threads],
        total=total,
        page=request.page,
        per_page=request.per_page,
    )


# --- Compose ---

@router.post("/compose", status_code=status.HTTP_201_CREATED)
async def compose_message(
    request: ComposeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compose a new message — saves as draft or sends via SMTP/Gmail."""
    from app.services.email_send import EmailSendService

    # Verify account belongs to user
    result = await db.execute(
        select(Account).where(Account.id == request.account_id, Account.user_id == user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if request.is_draft:
        # Just save as draft (existing logic)
        thread = None
        if request.in_reply_to_message_id:
            orig_result = await db.execute(
                select(Message).where(Message.id == request.in_reply_to_message_id)
            )
            orig_msg = orig_result.scalar_one_or_none()
            if orig_msg:
                thread_result = await db.execute(
                    select(Thread).where(Thread.id == orig_msg.thread_id)
                )
                thread = thread_result.scalar_one_or_none()

        if not thread:
            thread = Thread(
                user_id=user.id,
                subject=request.subject,
                message_count=0,
            )
            db.add(thread)
            await db.flush()

        message = Message(
            thread_id=thread.id,
            account_id=account.id,
            from_address=account.email_address,
            from_name=account.display_name,
            to_addresses=[a.model_dump() for a in request.to_addresses],
            cc_addresses=[a.model_dump() for a in request.cc_addresses],
            bcc_addresses=[a.model_dump() for a in request.bcc_addresses],
            subject=request.subject,
            body_html=request.body_html,
            body_text=request.body_text,
            is_draft=True,
            is_read=True,
        )
        db.add(message)
        await db.flush()
        await db.execute(
            sa_update(Thread)
            .where(Thread.id == thread.id)
            .values(message_count=Thread.message_count + 1)
        )
        await db.commit()
        await db.refresh(message)

        return {
            "message_id": str(message.id),
            "thread_id": str(thread.id),
            "status": "draft",
        }
    else:
        # Actually send the email
        sender = EmailSendService(db, account)

        # Look up in_reply_to header if replying
        in_reply_to_header = None
        references_header = None
        if request.in_reply_to_message_id:
            orig_result = await db.execute(
                select(Message).where(Message.id == request.in_reply_to_message_id)
            )
            orig_msg = orig_result.scalar_one_or_none()
            if orig_msg:
                in_reply_to_header = orig_msg.message_id_header
                references_header = orig_msg.references

        try:
            result = await sender.send(
                to=[a.model_dump() for a in request.to_addresses],
                subject=request.subject,
                body_html=request.body_html,
                body_text=request.body_text,
                cc=[a.model_dump() for a in request.cc_addresses],
                bcc=[a.model_dump() for a in request.bcc_addresses],
                in_reply_to=in_reply_to_header,
                references=references_header,
                signature_id=request.signature_id,
                read_receipt=request.read_receipt_requested,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Failed to send message: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send message. Please check your account settings and try again.",
            )

        return {
            "message_id": result["message_id"],
            "thread_id": result["thread_id"],
            "status": "sent",
        }

# --- Helpers ---

async def _propagate_label_change(
    db: AsyncSession,
    user_id,
    messages: list[Message],
    add_labels: list[str] = None,
    remove_labels: list[str] = None,
):
    """Fan out label changes (archive/trash) to each provider.
    Failures are logged but do not raise — local state is already committed,
    and a future sync via history.list will reconcile if the remote still diverges.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Group messages with remote_ids by account_id
    by_account: dict = {}
    for m in messages:
        if not m.remote_id:
            continue
        by_account.setdefault(m.account_id, []).append(m.remote_id)

    if not by_account:
        return

    account_result = await db.execute(
        select(Account).where(
            Account.id.in_(by_account.keys()),
            Account.user_id == user_id,
        )
    )
    for account in account_result.scalars().all():
        remote_ids = by_account.get(account.id, [])
        if not remote_ids:
            continue
        if account.provider == "gmail":
            from app.services.gmail_sync import GmailSyncService
            gmail = GmailSyncService(db, account)
            try:
                await gmail.batch_modify_labels(
                    remote_ids,
                    add_labels=add_labels,
                    remove_labels=remove_labels,
                )
            except Exception as e:
                logger.error(
                    "Failed to propagate label change to Gmail for %s: %s",
                    account.email_address, e,
                )
            finally:
                await gmail._close()
        # Stalwart/IMAP propagation deferred to a later phase


async def _get_thread_or_404(db, user_id, thread_id: str) -> Thread:
    result = await db.execute(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


async def _get_message_or_404(db, user_id, message_id: str) -> Message:
    result = await db.execute(
        select(Message)
        .where(
            Message.id == message_id,
            Message.account_id.in_(
                select(Account.id).where(Account.user_id == user_id)
            ),
        )
        .options(selectinload(Message.attachments))
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return msg


async def _get_user_messages(db, user_id, message_ids: list[str]) -> list[Message]:
    result = await db.execute(
        select(Message).where(
            Message.id.in_(message_ids),
            Message.account_id.in_(
                select(Account.id).where(Account.user_id == user_id)
            ),
        )
    )
    return list(result.scalars().all())


def _to_thread_response(t: Thread) -> ThreadResponse:
    messages = sorted(t.messages or [], key=lambda m: m.received_at or m.created_at, reverse=True)
    latest = messages[0] if messages else None
    has_unread = any(not m.is_read for m in messages)
    account_ids = list(set(str(m.account_id) for m in messages))

    return ThreadResponse(
        id=str(t.id),
        subject=t.subject,
        last_message_at=t.last_message_at,
        message_count=t.message_count,
        is_starred=t.is_starred,
        is_snoozed=t.is_snoozed,
        snoozed_until=t.snoozed_until,
        latest_from_name=latest.from_name if latest else None,
        latest_from_address=latest.from_address if latest else None,
        latest_snippet=latest.snippet if latest else None,
        has_unread=has_unread,
        account_ids=account_ids,
    )


def _to_thread_detail_response(t: Thread) -> ThreadDetailResponse:
    base = _to_thread_response(t)
    messages = sorted(t.messages or [], key=lambda m: m.received_at or m.created_at, reverse=True)

    return ThreadDetailResponse(
        **base.model_dump(),
        messages=[_to_message_detail(m) for m in messages],
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _to_message_detail(m: Message) -> MessageDetailResponse:
    return MessageDetailResponse(
        id=str(m.id),
        thread_id=str(m.thread_id),
        account_id=str(m.account_id),
        folder_id=str(m.folder_id) if m.folder_id else None,
        from_address=m.from_address,
        from_name=m.from_name,
        to_addresses=m.to_addresses or [],
        cc_addresses=m.cc_addresses or [],
        bcc_addresses=m.bcc_addresses or [],
        subject=m.subject,
        snippet=m.snippet,
        body_html=m.body_html,
        body_text=m.body_text,
        message_id_header=m.message_id_header,
        in_reply_to=m.in_reply_to,
        is_read=m.is_read,
        is_starred=m.is_starred,
        is_draft=m.is_draft,
        is_sent=m.is_sent,
        is_archived=m.is_archived,
        is_trashed=m.is_trashed,
        has_attachments=m.has_attachments,
        read_receipt_requested=m.read_receipt_requested,
        read_receipt_sent_at=m.read_receipt_sent_at,
        received_at=m.received_at,
        sent_at=m.sent_at,
        attachments=[
            AttachmentResponse(
                id=str(a.id),
                filename=a.filename,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
            )
            for a in (m.attachments or [])
        ],
        created_at=m.created_at,
    )
