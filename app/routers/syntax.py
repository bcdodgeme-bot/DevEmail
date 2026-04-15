"""
Syntax Prime integration — proxy routes for the external Syntax Prime AI service.

Keeps SYNTAX_URL server-side so it isn't exposed to the browser.

Payload forwarded to Syntax Prime's POST /api/draft-reply:
    {
      "subject": str,
      "sender_name": str,
      "sender_email": str,
      "thread_messages": [str, ...]   # most recent first, up to 3
    }

Expected response from Syntax Prime:
    { "draft": str }
"""

import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.middleware.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/syntax", tags=["syntax"])


class DraftReplyRequest(BaseModel):
    subject: str
    sender_name: str
    sender_email: str
    thread_messages: List[str]


class DraftReplyResponse(BaseModel):
    draft: str


@router.post("/draft-reply", response_model=DraftReplyResponse)
async def draft_reply(
    payload: DraftReplyRequest,
    user: User = Depends(get_current_user),
):
    """Proxy a draft-reply request to Syntax Prime."""
    if not settings.SYNTAX_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Syntax Prime integration is not configured",
        )

    url = f"{settings.SYNTAX_URL.rstrip('/')}/api/draft-reply"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload.model_dump())
    except httpx.RequestError as e:
        logger.error("Syntax Prime request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Syntax Prime",
        )

    if resp.status_code >= 400:
        logger.error("Syntax Prime returned %d: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Syntax Prime returned {resp.status_code}",
        )

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Syntax Prime returned invalid JSON",
        )

    draft = data.get("draft")
    if not isinstance(draft, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Syntax Prime response missing 'draft' string",
        )

    return DraftReplyResponse(draft=draft)
