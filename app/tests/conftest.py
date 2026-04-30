"""
Shared pytest fixtures.

The classifier's reply-history check uses Postgres-only `jsonb_array_elements`,
so DB-bound tests need a real Postgres. Set TEST_DATABASE_URL to opt in;
otherwise DB-bound tests skip cleanly and the pure-Python tests still run.

Example:
    TEST_DATABASE_URL=postgresql+asyncpg://localhost/devemail_test pytest

Project imports (database, models, pydantic-settings via app.config) are
performed lazily inside fixtures so the pure-Python test classes can run
even in environments where the full app dependency stack is not installed.
"""
from __future__ import annotations

import os
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _requires_db():
    return pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="TEST_DATABASE_URL not set — set it to a Postgres DB to run DB-bound tests",
    )


# Re-export so individual test files can use @requires_db
requires_db = _requires_db()


@pytest_asyncio.fixture(scope="session")
async def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not configured", allow_module_level=False)
    # Lazy imports — only resolve project deps when the DB fixture is used.
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.database import Base  # noqa: F401
    # Importing models registers them on Base.metadata for create_all.
    from app.models import (  # noqa: F401
        User, Account, Folder, Thread, Message, SenderClassification,
        Signature, Attachment, Contact, Calendar, Event,
        NotificationPreference, UnsubscribeLink, ApiKey, OpenEvent,
        RefreshToken,
    )

    eng = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """Per-test session inside a rolled-back transaction."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with Session(bind=conn) as session:
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()


@pytest_asyncio.fixture
async def user(db):
    from app.models.user import User
    u = User(
        id=uuid.uuid4(),
        email=f"u-{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def other_user(db):
    from app.models.user import User
    u = User(
        id=uuid.uuid4(),
        email=f"u-{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
    )
    db.add(u)
    await db.flush()
    return u


async def _make_account(db, user_id: uuid.UUID, *, email: str):
    from app.models.account import Account
    a = Account(
        id=uuid.uuid4(),
        user_id=user_id,
        provider="gmail",
        email_address=email,
        auth_type="oauth",
    )
    db.add(a)
    await db.flush()
    return a


@pytest_asyncio.fixture
async def account_a(db, user):
    return await _make_account(db, user.id, email="alice-a@test.local")


@pytest_asyncio.fixture
async def account_b(db, user):
    return await _make_account(db, user.id, email="alice-b@test.local")
