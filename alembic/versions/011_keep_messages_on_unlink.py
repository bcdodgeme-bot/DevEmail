"""keep synced messages when an account is unlinked

Revision ID: keep_messages_on_unlink
Revises: lowercase_addresses
Create Date: 2026-06-17

Unlinking an account deletes the account row (so we don't retain IMAP
credentials) but should KEEP the messages that were synced from it. They
become orphaned-but-visible in the inbox.

To allow that, messages.account_id must permit NULL, and its FK to
accounts must SET NULL on delete instead of CASCADE (which previously
wiped the messages along with the account).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'keep_messages_on_unlink'
down_revision: Union[str, None] = 'lowercase_addresses'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow orphaned messages (account_id = NULL once the account is gone).
    op.alter_column('messages', 'account_id', nullable=True)

    # Swap the CASCADE FK for SET NULL so deleting an account orphans its
    # messages instead of deleting them. Constraint uses Postgres's default
    # auto-generated name (schema created via Base.metadata.create_all).
    op.drop_constraint('messages_account_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key(
        'messages_account_id_fkey',
        'messages',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # Reverting requires every message to have an account again. Orphaned
    # rows (account_id IS NULL) would violate the NOT NULL we restore below,
    # so drop them — they cannot be reattached to a deleted account.
    op.execute("DELETE FROM messages WHERE account_id IS NULL")

    op.drop_constraint('messages_account_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key(
        'messages_account_id_fkey',
        'messages',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.alter_column('messages', 'account_id', nullable=False)
