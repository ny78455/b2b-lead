"""
models.py — SQLAlchemy ORM models matching the data contracts in §5 of the spec.

Tables:
  companies        — enriched lead record
  contacts         — business contact linked to a company
  campaigns        — email draft lifecycle (pending_review → approved → sent)
  replies          — classified inbound replies
  suppression_list — opt-out / bounce registry; checked before every send
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, String, Text, Float, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── companies ─────────────────────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512))
    industry: Mapped[str | None] = mapped_column(String(128))
    employees_estimate: Mapped[str | None] = mapped_column(String(64))   # e.g. "11-50"
    summary: Mapped[str | None] = mapped_column(Text)
    tech_stack_hints: Mapped[str | None] = mapped_column(Text)

    # Module 3 — RAG score
    rag_score: Mapped[int | None] = mapped_column(Integer)
    rag_rationale: Mapped[str | None] = mapped_column(Text)

    # Module 4 — purchase intent score (rule-based)
    purchase_score: Mapped[int | None] = mapped_column(Integer)

    # Module 5 — persona summary
    persona_summary: Mapped[str | None] = mapped_column(Text)

    # Pipeline state
    enrichment_status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending | done | failed
    status: Mapped[str] = mapped_column(
        String(32), default="new"
    )  # new | enriched | drafted | sent

    # Google Maps / scraper metadata
    phone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(512))
    google_maps_url: Mapped[str | None] = mapped_column(String(1024))
    search_query: Mapped[str | None] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="company", cascade="all, delete-orphan")


# ── contacts ──────────────────────────────────────────────────────────────────

class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    confidence: Mapped[str | None] = mapped_column(String(32))  # high | medium | low
    source: Mapped[str | None] = mapped_column(String(64))      # e.g. "homepage_scrape"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="contacts")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="contact")


# ── campaigns ─────────────────────────────────────────────────────────────────

CAMPAIGN_STATUSES = ("pending_review", "approved", "sent", "rejected")

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))

    subject: Mapped[str | None] = mapped_column(String(512))
    draft_html: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(32), default="pending_review", index=True
    )  # pending_review | approved | sent | rejected
    
    draft_source: Mapped[str | None] = mapped_column(String(64))  # e.g. "gemini" | "template_fallback"

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # SendGrid tracking
    sendgrid_message_id: Mapped[str | None] = mapped_column(String(256))

    # Follow-up placeholder (post-MVP)
    next_followup_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="campaigns")
    contact: Mapped["Contact | None"] = relationship(back_populates="campaigns")
    replies: Mapped[list["Reply"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


# ── replies ───────────────────────────────────────────────────────────────────

REPLY_CLASSIFICATIONS = ("interested", "not_interested", "needs_info", "auto_reply_or_oof")
REPLY_SENTIMENTS = ("positive", "neutral", "negative")

class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))

    raw_text: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(32))  # see REPLY_CLASSIFICATIONS
    sentiment: Mapped[str | None] = mapped_column(String(16))       # see REPLY_SENTIMENTS

    # IMAP metadata
    imap_message_id: Mapped[str | None] = mapped_column(String(512))
    from_email: Mapped[str | None] = mapped_column(String(320))

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="replies")


# ── suppression_list ──────────────────────────────────────────────────────────

class SuppressionEntry(Base):
    __tablename__ = "suppression_list"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(128))  # e.g. "unsubscribe" | "bounce" | "manual"
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
