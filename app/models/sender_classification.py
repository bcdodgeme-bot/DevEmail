import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SenderClassification(Base):
    __tablename__ = "sender_classifications"
    __table_args__ = (
        # One rule per (account, address, scope). is_domain_rule is part of the
        # key so an address-level and domain-level rule can coexist.
        UniqueConstraint(
            "account_id", "sender_address", "is_domain_rule",
            name="uq_sender_classifications_account_address_scope",
        ),
        # Composite index for domain-rule lookups during classification.
        Index(
            "ix_sender_classifications_account_domain_scope",
            "account_id", "sender_domain", "is_domain_rule",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_address: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    sender_domain: Mapped[str | None] = mapped_column(String(255))
    is_domain_rule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    learned_from: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
