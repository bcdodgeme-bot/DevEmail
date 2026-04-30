import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("account_id", "remote_id", name="uq_messages_account_remote"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"))
    remote_id: Mapped[str | None] = mapped_column(String)
    remote_thread_id: Mapped[str | None] = mapped_column(String, index=True)
    message_id_header: Mapped[str | None] = mapped_column(String)
    in_reply_to: Mapped[str | None] = mapped_column(String)
    references: Mapped[str | None] = mapped_column("references", String)
    from_address: Mapped[str | None] = mapped_column(String(255))
    from_name: Mapped[str | None] = mapped_column(String(255))
    to_addresses: Mapped[dict] = mapped_column(JSONB, default=list)
    cc_addresses: Mapped[dict] = mapped_column(JSONB, default=list)
    bcc_addresses: Mapped[dict] = mapped_column(JSONB, default=list)
    subject: Mapped[str | None] = mapped_column(String)
    body_html: Mapped[str | None] = mapped_column(String)
    body_text: Mapped[str | None] = mapped_column(String)
    snippet: Mapped[str | None] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    read_receipt_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    read_receipt_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Unique token for the tracking pixel URL on sent mail (open tracking).
    # Indirects message.id so the internal UUID isn't leaked in the pixel URL.
    tracking_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # People/Bulk classification — populated at sync time by the classifier
    # gauntlet (override → reply history → header rules → default).
    category: Mapped[str] = mapped_column(String(16), nullable=False, server_default="people", index=True)
    category_source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="default")

    # Relationships
    thread = relationship("Thread", back_populates="messages")
    account = relationship("Account", back_populates="messages")
    folder = relationship("Folder", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", lazy="selectin")
    unsubscribe_links = relationship("UnsubscribeLink", back_populates="message", lazy="selectin")
    open_events = relationship(
        "OpenEvent",
        back_populates="message",
        lazy="selectin",
        order_by="OpenEvent.opened_at",
    )
