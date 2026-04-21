import os
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, and_

from app.config import settings
from app.database import async_session
from app.models.account import Account
from app.models.thread import Thread
from app.services.imap_sync import sync_account
from app.services.gmail_sync import GmailSyncService
from app.routers import auth, contacts, health, accounts, messages, calendars, sync, preferences
from app.routers import notifications, api_keys, syntax, tracking

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 300  # 5 minutes
SNOOZE_CHECK_INTERVAL_SECONDS = 60  # 1 minute
SYNC_MAX_FAILURES = 5          # disable account after this many consecutive failures
SYNC_BACKOFF_BASE = 60         # start backoff at 60s, doubling each failure

REMINDER_CHECK_INTERVAL_SECONDS = 60  # check every minute
REMINDER_OFFSETS = [60, 30, 10]       # minutes before event

# Track per-account consecutive failure counts and backoff expiry
_sync_failures: dict[str, int] = defaultdict(int)
_sync_backoff_until: dict[str, float] = {}


# --------------------------------------------------
# Background Tasks
# --------------------------------------------------

async def periodic_sync():
    """Background task that syncs all enabled accounts every 5 minutes."""
    import time
    # Wait a bit on startup to let the app fully initialize
    await asyncio.sleep(10)
    logger.info("Background sync task started (every %d seconds)", SYNC_INTERVAL_SECONDS)

    while True:
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Account).where(Account.sync_enabled == True)
                )
                accounts_list = result.scalars().all()

                if not accounts_list:
                    logger.info("No sync-enabled accounts found, skipping")
                else:
                    for account in accounts_list:
                        account_key = str(account.id)
                        now = time.monotonic()

                        # Skip if in backoff window
                        if _sync_backoff_until.get(account_key, 0) > now:
                            remaining = int(_sync_backoff_until[account_key] - now)
                            logger.info("Skipping %s — backoff for %ds more", account.email_address, remaining)
                            continue

                        try:
                            if account.provider == "gmail":
                                await _sync_gmail_account(db, account)
                            else:
                                summary = await sync_account(account, account.user_id, db)
                                logger.info(
                                    "Auto-sync %s: fetched=%s new=%s skipped=%s",
                                    account.email_address,
                                    summary.get("fetched", 0),
                                    summary.get("new", 0),
                                    summary.get("skipped", 0),
                                )
                            # Reset failure count on success
                            _sync_failures[account_key] = 0
                            _sync_backoff_until.pop(account_key, None)
                        except Exception as e:
                            failures = _sync_failures[account_key] + 1
                            _sync_failures[account_key] = failures
                            backoff = min(SYNC_BACKOFF_BASE * (2 ** (failures - 1)), 3600)
                            _sync_backoff_until[account_key] = now + backoff
                            logger.error(
                                "Auto-sync failed for %s (failure %d/%d, backoff %ds): %s",
                                account.email_address, failures, SYNC_MAX_FAILURES, backoff, e,
                            )
                            if failures >= SYNC_MAX_FAILURES:
                                logger.error(
                                    "Disabling sync for %s after %d consecutive failures",
                                    account.email_address, failures,
                                )
                                account.sync_enabled = False
                                await db.commit()
        except Exception as e:
            logger.error("Background sync error: %s", e)

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


async def _sync_gmail_account(db, account: Account):
    """Sync a Gmail account using the Gmail API."""
    gmail = GmailSyncService(db, account)
    try:
        await gmail.sync_labels()
        new_count = await gmail.sync_incremental()
        logger.info(
            "Auto-sync Gmail %s: new=%d",
            account.email_address,
            new_count,
        )
    finally:
        await gmail._close()


def _in_quiet_hours(pref, now: datetime) -> bool:
    """Return True if current UTC time falls within the user's quiet hours window."""
    if not pref.quiet_hours_start or not pref.quiet_hours_end:
        return False
    current = now.time()
    start = pref.quiet_hours_start
    end = pref.quiet_hours_end
    if start <= end:
        return start <= current <= end
    # Wraps midnight (e.g. 22:00–06:00)
    return current >= start or current <= end


async def meeting_reminders():
    """Background task that creates calendar_reminder notifications 60/30/10 min before events."""
    from app.models.calendar import Event, Calendar
    from app.models.notification import Notification, NotificationPreference

    await asyncio.sleep(20)
    logger.info("Meeting reminders task started (every %d seconds)", REMINDER_CHECK_INTERVAL_SECONDS)

    while True:
        try:
            now = datetime.now(timezone.utc)
            async with async_session() as db:
                prefs_result = await db.execute(
                    select(NotificationPreference).where(
                        NotificationPreference.notify_calendar_reminder == True
                    )
                )
                prefs = prefs_result.scalars().all()

                created_count = 0
                for pref in prefs:
                    if _in_quiet_hours(pref, now):
                        continue

                    for offset_mins in REMINDER_OFFSETS:
                        target = now + timedelta(minutes=offset_mins)
                        window_start = target - timedelta(seconds=90)
                        window_end = target + timedelta(seconds=90)

                        events_result = await db.execute(
                            select(Event)
                            .join(Calendar, Event.calendar_id == Calendar.id)
                            .where(
                                Calendar.user_id == pref.user_id,
                                Event.start_at >= window_start,
                                Event.start_at <= window_end,
                                Event.all_day == False,
                            )
                        )
                        events = events_result.scalars().all()

                        for event in events:
                            ref_id = f"{event.id}:{offset_mins}"

                            existing = await db.execute(
                                select(Notification.id).where(
                                    Notification.user_id == pref.user_id,
                                    Notification.category == "calendar_reminder",
                                    Notification.reference_id == ref_id,
                                ).limit(1)
                            )
                            if existing.scalar_one_or_none():
                                continue

                            label = f"{offset_mins} minute{'s' if offset_mins != 1 else ''}"
                            body = event.location or event.conference_link or None
                            db.add(Notification(
                                user_id=pref.user_id,
                                category="calendar_reminder",
                                title=f"Meeting in {label}: {event.title}",
                                body=body,
                                reference_id=ref_id,
                            ))
                            created_count += 1

                if created_count:
                    await db.commit()
                    logger.info("Created %d meeting reminder notification(s)", created_count)
        except Exception as e:
            logger.error("Meeting reminders error: %s", e)

        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


async def snooze_wakeup():
    """Background task that un-snoozes threads whose snooze time has expired."""
    await asyncio.sleep(15)
    logger.info("Snooze wake-up task started (every %d seconds)", SNOOZE_CHECK_INTERVAL_SECONDS)

    while True:
        try:
            now = datetime.now(timezone.utc)
            async with async_session() as db:
                result = await db.execute(
                    select(Thread).where(
                        and_(
                            Thread.is_snoozed == True,
                            Thread.snoozed_until != None,
                            Thread.snoozed_until <= now,
                        )
                    )
                )
                expired_threads = result.scalars().all()

                if expired_threads:
                    for thread in expired_threads:
                        thread.is_snoozed = False
                        thread.snoozed_until = None
                    await db.commit()
                    logger.info("Un-snoozed %d thread(s)", len(expired_threads))
        except Exception as e:
            logger.error("Snooze wake-up error: %s", e)

        await asyncio.sleep(SNOOZE_CHECK_INTERVAL_SECONDS)


# --------------------------------------------------
# App Lifecycle
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle manager."""
    # Startup: launch background tasks
    sync_task = asyncio.create_task(periodic_sync())
    snooze_task = asyncio.create_task(snooze_wakeup())
    reminder_task = asyncio.create_task(meeting_reminders())
    logger.info("DevEmail started — background tasks launched")
    yield
    # Shutdown: cancel background tasks
    sync_task.cancel()
    snooze_task.cancel()
    reminder_task.cancel()
    for task in (sync_task, snooze_task, reminder_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Background tasks stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-API-Key"],
)

# Routers
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(calendars.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(api_keys.router, prefix="/api")
app.include_router(syntax.router, prefix="/api")
app.include_router(tracking.router, prefix="/api")


# --------------------------------------------------
# Static file serving for React frontend
# --------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

logger.debug("STATIC_DIR=%s, exists=%s", STATIC_DIR, os.path.exists(STATIC_DIR))

if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept unmatched API routes — return 404 instead of index.html
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

else:
    @app.get("/")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": "0.1.0",
            "docs": "/api/docs",
        }
