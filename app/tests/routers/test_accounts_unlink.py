"""Unlinking an account keeps its synced messages (orphaned, not deleted).

Exercises the same DB operation the DELETE /accounts/{id} endpoint performs
(db.delete(account); commit) and asserts the messages survive with a NULL
account_id thanks to the ON DELETE SET NULL FK.
"""
import uuid

import pytest
from sqlalchemy import select

from app.tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_unlink_keeps_messages_orphaned(db, user, account_a):
    from app.models.thread import Thread
    from app.models.message import Message
    from app.models.account import Account

    thread = Thread(id=uuid.uuid4(), user_id=user.id, subject="kept")
    db.add(thread)
    await db.flush()

    msg = Message(
        id=uuid.uuid4(),
        thread_id=thread.id,
        account_id=account_a.id,
        subject="hello",
    )
    db.add(msg)
    await db.flush()

    # Same operation as the unlink endpoint.
    await db.delete(account_a)
    await db.flush()

    # Account is gone...
    assert (await db.execute(
        select(Account).where(Account.id == account_a.id)
    )).scalar_one_or_none() is None

    # ...but the message survives, orphaned (account_id nulled out).
    kept = (await db.execute(
        select(Message).where(Message.id == msg.id)
    )).scalar_one_or_none()
    assert kept is not None
    assert kept.account_id is None

    # ...and so does its thread.
    assert (await db.execute(
        select(Thread).where(Thread.id == thread.id)
    )).scalar_one_or_none() is not None
