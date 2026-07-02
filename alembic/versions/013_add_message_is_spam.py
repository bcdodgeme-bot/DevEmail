"""add messages.is_spam for Junk-folder mail + the Spam action

Revision ID: add_message_is_spam
Revises: keep_signatures_on_unlink
Create Date: 2026-06-25

Folder-aware IMAP sync files Junk-folder mail with is_spam=true, and the
(upcoming) Spam button sets it. The inbox view excludes is_spam the same way
it excludes is_trashed / is_archived, and a dedicated Junk view surfaces it.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'add_message_is_spam'
down_revision: Union[str, None] = 'keep_signatures_on_unlink'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('is_spam', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_messages_is_spam', 'messages', ['is_spam'])


def downgrade() -> None:
    op.drop_index('ix_messages_is_spam', table_name='messages')
    op.drop_column('messages', 'is_spam')
