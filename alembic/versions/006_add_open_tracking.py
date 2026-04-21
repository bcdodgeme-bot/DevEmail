"""add open tracking (tracking_token on messages + open_events table)

Revision ID: add_open_tracking
Revises: add_inline_image_fields
Create Date: 2026-04-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_open_tracking'
down_revision: Union[str, None] = 'add_inline_image_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('tracking_token', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        'ix_messages_tracking_token',
        'messages',
        ['tracking_token'],
        unique=True,
    )

    op.create_table(
        'open_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'message_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('messages.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'opened_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
    )
    op.create_index('ix_open_events_message_id', 'open_events', ['message_id'])


def downgrade() -> None:
    op.drop_index('ix_open_events_message_id', table_name='open_events')
    op.drop_table('open_events')
    op.drop_index('ix_messages_tracking_token', table_name='messages')
    op.drop_column('messages', 'tracking_token')
