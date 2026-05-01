"""one-time data migration: lowercase existing message addresses

Revision ID: lowercase_addresses
Revises: add_sent_partial_index
Create Date: 2026-04-30

Phase 8 cleanup pass. From Phase 8 onward all five write paths normalize
addresses on insert (.strip().lower()), and the EmailAddress Pydantic
schema lowercases on validate. This migration brings legacy rows into
line so query-time case-insensitive match isn't strictly required.

Touches messages.from_address (text) and messages.to_addresses /
cc_addresses / bcc_addresses (JSONB lists of {"name", "address"} objects).
sender_classifications.sender_address is intentionally NOT touched —
Phase 4's manual-move handler already lowercases at write. If any rule
slipped through with mixed case, that's a separate bug; verify with
SELECT * FROM sender_classifications WHERE sender_address != lower(sender_address);
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'lowercase_addresses'
down_revision: Union[str, None] = 'add_sent_partial_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# JSONB column rewrite — applied identically to to_addresses, cc_addresses,
# bcc_addresses. Selects only rows that actually need change to keep the
# write set small.
_JSONB_COL_TEMPLATE = """
UPDATE messages
SET {col} = COALESCE(
    (
        SELECT jsonb_agg(
            CASE
                WHEN jsonb_typeof(elem) = 'object' AND elem ? 'address'
                THEN jsonb_set(elem, '{{address}}', to_jsonb(lower(elem->>'address')))
                ELSE elem
            END
        )
        FROM jsonb_array_elements({col}) AS elem
    ),
    '[]'::jsonb
)
WHERE {col} IS NOT NULL
  AND jsonb_typeof({col}) = 'array'
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements({col}) AS elem
      WHERE jsonb_typeof(elem) = 'object'
        AND elem ? 'address'
        AND elem->>'address' IS DISTINCT FROM lower(elem->>'address')
  );
"""


def upgrade() -> None:
    # Plain text column.
    op.execute(
        """
        UPDATE messages
        SET from_address = lower(from_address)
        WHERE from_address IS NOT NULL
          AND from_address <> lower(from_address);
        """
    )

    for col in ("to_addresses", "cc_addresses", "bcc_addresses"):
        op.execute(_JSONB_COL_TEMPLATE.format(col=col))


def downgrade() -> None:
    # Lowercasing is information-destroying. There's no faithful inverse —
    # this migration intentionally has no downgrade. Leaving as a no-op so
    # `alembic downgrade` doesn't crash if someone runs it accidentally.
    pass
