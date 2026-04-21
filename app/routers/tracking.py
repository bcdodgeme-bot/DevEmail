"""Open-tracking pixel endpoint.

Unauthenticated: the pixel fires from the recipient's mail client, which has
no session. We look up the message by its tracking_token (unguessable UUID)
and record an OpenEvent, then return a 1x1 transparent GIF.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.message import Message
from app.models.open_event import OpenEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/track", tags=["tracking"])

# 1x1 transparent GIF (43 bytes, GIF89a)
_PIXEL_GIF = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00,
    0x01, 0x00, 0x80, 0x00, 0x00, 0xff, 0xff, 0xff,
    0x00, 0x00, 0x00, 0x21, 0xf9, 0x04, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b,
])

_PIXEL_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Content-Type": "image/gif",
}


def _pixel_response() -> Response:
    return Response(content=_PIXEL_GIF, media_type="image/gif", headers=_PIXEL_HEADERS)


@router.get("/open/{token}")
async def track_open(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Record an open event for the message identified by this token.
    Always returns a 1x1 pixel — even on errors — so the mail client
    doesn't show a broken image."""
    try:
        token_uuid = uuid.UUID(token)
    except (ValueError, TypeError):
        return _pixel_response()

    result = await db.execute(
        select(Message.id).where(Message.tracking_token == token_uuid)
    )
    message_id = result.scalar_one_or_none()
    if not message_id:
        return _pixel_response()

    user_agent = request.headers.get("user-agent", "")[:500] or None
    # X-Forwarded-For may contain a comma-separated chain; take the first.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        ip = xff.split(",")[0].strip()[:45]
    else:
        ip = request.client.host[:45] if request.client else None

    try:
        db.add(OpenEvent(
            message_id=message_id,
            user_agent=user_agent,
            ip=ip,
        ))
        await db.commit()
    except Exception as e:
        logger.warning("Failed to record open event for %s: %s", token_uuid, e)
        await db.rollback()

    return _pixel_response()
