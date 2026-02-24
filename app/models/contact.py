import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cloze_id: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    middle_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(500))
    headline: Mapped[str | None] = mapped_column(String)
    company: Mapped[str | None] = mapped_column(String(500))
    job_title: Mapped[str | None] = mapped_column(String(500))
    department: Mapped[str | None] = mapped_column(String(255))
    custom_role: Mapped[str | None] = mapped_column(String(255))
    emails: Mapped[dict] = mapped_column(JSONB, default=list)
    phones: Mapped[dict] = mapped_column(JSONB, default=list)
    addresses: Mapped[dict] = mapped_column(JSONB, default=list)
    social_profiles: Mapped[dict] = mapped_column(JSONB, default=list)
    websites: Mapped[dict] = mapped_column(JSONB, default=list)
    tags: Mapped[dict] = mapped_column(JSONB, default=list)
    location: Mapped[str | None] = mapped_column(String(500))
    location_country: Mapped[str | None] = mapped_column(String(255))
    birthday: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(50))
    segment: Mapped[str | None] = mapped_column(String(100))
    stage: Mapped[str | None] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String)
    company_domain = Column(String(255), nullable=True)
    enrichment_data = Column(Text, nullable=True)
    enriched = Column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    first_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_interaction_type: Mapped[str | None] = mapped_column(String(50))
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_interaction_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="contacts")
