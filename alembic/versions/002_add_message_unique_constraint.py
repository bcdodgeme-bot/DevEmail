"""add unique constraint on messages(account_id, remote_id)

Revision ID: add_message_unique_constraint
Revises: add_password_hash
Create Date: 2026-03-15

Prevents duplicate message sync when concurrent syncs run.
remote_id is NULL for locally-composed messages — PostgreSQL
does not enforce uniqueness for NULL values, so those rows
are unaffected.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'add_message_unique_constraint'
down_revision: Union[str, None] = 'add_password_hash'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any existing duplicates first (keep the earliest by created_at)
    op.execute("""
        DELETE FROM messages
        WHERE id NOT IN (
            SELECT DISTINCT ON (account_id, remote_id) id
            FROM messages
            WHERE remote_id IS NOT NULL
            ORDER BY account_id, remote_id, created_at ASC
        )
        AND remote_id IS NOT NULL
    """)
    op.create_unique_constraint(
        'uq_messages_account_remote',
        'messages',
        ['account_id', 'remote_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_messages_account_remote', 'messages', type_='unique')
