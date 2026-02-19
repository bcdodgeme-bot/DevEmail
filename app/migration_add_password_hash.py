"""add password_hash to users

Revision ID: add_password_hash
Revises: <REPLACE_WITH_YOUR_LATEST_REVISION_ID>
Create Date: 2026-02-19

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'add_password_hash'
down_revision: Union[str, None] = None  # <-- UPDATE THIS to your latest revision ID
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_hash')
