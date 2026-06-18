"""keep signatures when an account is unlinked

Revision ID: keep_signatures_on_unlink
Revises: keep_messages_on_unlink
Create Date: 2026-06-18

Companion to keep_messages_on_unlink. Unlinking an account deletes the
account row, but signatures.account_id was NOT NULL with ON DELETE CASCADE.
The Account.signatures relationship is lazy="selectin" (eagerly loaded) with
no passive_deletes, so SQLAlchemy nullifies the loaded signature rows on
db.delete(account) — which blew up against the NOT NULL constraint (500).

Mirror the messages fix: make signatures.account_id nullable and switch its
FK to SET NULL so signatures are orphaned-but-kept instead of deleted.
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'keep_signatures_on_unlink'
down_revision: Union[str, None] = 'keep_messages_on_unlink'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow orphaned signatures (account_id = NULL once the account is gone).
    op.alter_column('signatures', 'account_id', nullable=True)

    # Swap the CASCADE FK for SET NULL. Constraint uses Postgres's default
    # auto-generated name (schema created via Base.metadata.create_all).
    op.drop_constraint('signatures_account_id_fkey', 'signatures', type_='foreignkey')
    op.create_foreign_key(
        'signatures_account_id_fkey',
        'signatures',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # Orphaned rows (account_id IS NULL) would violate the restored NOT NULL,
    # and can't be reattached to a deleted account — drop them.
    op.execute("DELETE FROM signatures WHERE account_id IS NULL")

    op.drop_constraint('signatures_account_id_fkey', 'signatures', type_='foreignkey')
    op.create_foreign_key(
        'signatures_account_id_fkey',
        'signatures',
        'accounts',
        ['account_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.alter_column('signatures', 'account_id', nullable=False)
