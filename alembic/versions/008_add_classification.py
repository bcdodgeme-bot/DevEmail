"""add People/Bulk classification: messages.category + sender_classifications table

Revision ID: add_classification
Revises: fix_us_holidays_remote_id
Create Date: 2026-04-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'add_classification'
down_revision: Union[str, None] = 'fix_us_holidays_remote_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- messages: category + category_source -----
    # server_default ensures existing rows backfill to 'people' / 'default'
    # without a follow-up UPDATE. Phase 5's backfill will reclassify them.
    op.add_column(
        'messages',
        sa.Column(
            'category',
            sa.String(length=16),
            nullable=False,
            server_default='people',
        ),
    )
    op.add_column(
        'messages',
        sa.Column(
            'category_source',
            sa.String(length=16),
            nullable=False,
            server_default='default',
        ),
    )
    op.create_index('ix_messages_category', 'messages', ['category'])

    # ----- sender_classifications -----
    op.create_table(
        'sender_classifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'account_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('accounts.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('sender_address', sa.String(length=320), nullable=False),
        sa.Column('sender_domain', sa.String(length=255), nullable=True),
        sa.Column(
            'is_domain_rule',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column('category', sa.String(length=16), nullable=False),
        sa.Column('learned_from', sa.String(length=32), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            'account_id', 'sender_address', 'is_domain_rule',
            name='uq_sender_classifications_account_address_scope',
        ),
    )
    op.create_index(
        'ix_sender_classifications_account_id',
        'sender_classifications',
        ['account_id'],
    )
    op.create_index(
        'ix_sender_classifications_sender_address',
        'sender_classifications',
        ['sender_address'],
    )
    op.create_index(
        'ix_sender_classifications_account_domain_scope',
        'sender_classifications',
        ['account_id', 'sender_domain', 'is_domain_rule'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_sender_classifications_account_domain_scope',
        table_name='sender_classifications',
    )
    op.drop_index(
        'ix_sender_classifications_sender_address',
        table_name='sender_classifications',
    )
    op.drop_index(
        'ix_sender_classifications_account_id',
        table_name='sender_classifications',
    )
    op.drop_table('sender_classifications')

    op.drop_index('ix_messages_category', table_name='messages')
    op.drop_column('messages', 'category_source')
    op.drop_column('messages', 'category')
