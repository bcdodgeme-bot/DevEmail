import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select, and_

from app.config import settings
from app.database import async_session
from app.models.account import Account
from app.models.thread import Thread
from app.services.imap_sync import sync_account
from app.services.gmail_sync import GmailSyncService
from app.routers import auth, contacts, health, accounts, messages, calendars, sync, preferences
from app.routers import notifications

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 300  # 5 minutes
SNOOZE_CHECK_INTERVAL_SECONDS = 60  # 1 minute


# --------------------------------------------------
# Background Tasks
# --------------------------------------------------

async def periodic_sync():
    """Background task that syncs all enabled accounts every 5 minutes."""
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
                        except Exception as e:
                            logger.error("Auto-sync failed for %s: %s", account.email_address, e)
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
    logger.info("DevEmail started — background tasks launched")
    yield
    # Shutdown: cancel background tasks
    sync_task.cancel()
    snooze_task.cancel()
    for task in (sync_task, snooze_task):
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# --------------------------------------------------
# Static file serving for React frontend
# --------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

logging.info(f"STATIC_DIR={STATIC_DIR}, exists={os.path.exists(STATIC_DIR)}")
if os.path.exists(STATIC_DIR):
    logging.info(f"Static dir contents: {os.listdir(STATIC_DIR)}")

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
