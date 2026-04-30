"""fix US Holidays calendar remote_id (en.usa → en.usa#holiday@group.v.calendar.google.com)

Revision ID: fix_us_holidays_remote_id
Revises: add_open_tracking
Create Date: 2026-04-30
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'fix_us_holidays_remote_id'
down_revision: Union[str, None] = 'add_open_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BAD_ID = 'en.usa'
_GOOD_ID = 'en.usa#holiday@group.v.calendar.google.com'


def upgrade() -> None:
    # Some calendars rows were inserted with a truncated remote_id ('en.usa')
    # which Google's /calendars/{id}/events endpoint rejects with 404. The
    # canonical ID for US Holidays is en.usa#holiday@group.v.calendar.google.com.
    op.execute(
        f"""
        UPDATE calendars
        SET remote_id = '{_GOOD_ID}'
        WHERE remote_id = '{_BAD_ID}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE calendars
        SET remote_id = '{_BAD_ID}'
        WHERE remote_id = '{_GOOD_ID}'
        """
    )
