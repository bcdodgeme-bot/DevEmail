"""add inline image fields to attachments

Revision ID: add_inline_image_fields
Revises: add_api_keys
Create Date: 2026-04-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_inline_image_fields'
down_revision: Union[str, None] = 'add_api_keys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'attachments',
        sa.Column('content_id', sa.String(255), nullable=True),
    )
    op.add_column(
        'attachments',
        sa.Column(
            'is_inline',
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        'ix_attachments_message_content_id',
        'attachments',
        ['message_id', 'content_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_attachments_message_content_id', table_name='attachments')
    op.drop_column('attachments', 'is_inline')
    op.drop_column('attachments', 'content_id')
