"""add gmail_history_id to accounts

Revision ID: add_gmail_history_id
Revises: add_message_unique_constraint
Create Date: 2026-04-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_gmail_history_id'
down_revision: Union[str, None] = 'add_message_unique_constraint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('gmail_history_id', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'gmail_history_id')
