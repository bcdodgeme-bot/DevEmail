"""partial index on (account_id, is_sent) WHERE is_sent for classifier reply-history lookup

Revision ID: add_sent_partial_index
Revises: add_classification
Create Date: 2026-04-30
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'add_sent_partial_index'
down_revision: Union[str, None] = 'add_classification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Narrow partial index — sent volume is tiny vs. received, so this index
    # stays small and lets the reply-history scan jump straight to candidate
    # rows before the JSONB containment filter runs.
    op.create_index(
        'ix_messages_account_is_sent',
        'messages',
        ['account_id'],
        postgresql_where='is_sent = true',
    )


def downgrade() -> None:
    op.drop_index('ix_messages_account_is_sent', table_name='messages')
