"""
schemas.py — Pydantic request/response schemas for all API endpoints.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Contact
# ═══════════════════════════════════════════════════════════════════════════════

class ContactBase(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: str
    confidence: Optional[str] = None
    source: Optional[str] = None


class ContactCreate(ContactBase):
    company_id: uuid.UUID


class ContactOut(ContactBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Company
# ═══════════════════════════════════════════════════════════════════════════════

class CompanyBase(BaseModel):
    name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    search_query: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyOut(CompanyBase):
    id: uuid.UUID
    industry: Optional[str] = None
    employees_estimate: Optional[str] = None
    summary: Optional[str] = None
    tech_stack_hints: Optional[str] = None
    rag_score: Optional[int] = None
    rag_rationale: Optional[str] = None
    purchase_score: Optional[int] = None
    persona_summary: Optional[str] = None
    enrichment_status: str
    status: str
    created_at: datetime
    updated_at: datetime
    contacts: List[ContactOut] = []

    model_config = {"from_attributes": True}


class CompanyListItem(BaseModel):
    """Lightweight company row for the CRM table view."""
    id: uuid.UUID
    name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    rag_score: Optional[int] = None
    purchase_score: Optional[int] = None
    enrichment_status: str
    status: str
    email: Optional[str] = None   # primary contact email
    updated_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Campaign
# ═══════════════════════════════════════════════════════════════════════════════

class CampaignOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    subject: Optional[str] = None
    draft_html: Optional[str] = None
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None
    next_followup_date: Optional[datetime] = None
    company: Optional[CompanyOut] = None

    model_config = {"from_attributes": True}


class CampaignEditRequest(BaseModel):
    draft_html: str
    subject: Optional[str] = None


class CampaignPendingItem(BaseModel):
    """Used in the review queue list."""
    id: uuid.UUID
    company_name: str
    contact_email: Optional[str] = None
    subject: Optional[str] = None
    rag_score: Optional[int] = None
    purchase_score: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Reply
# ═══════════════════════════════════════════════════════════════════════════════

class ReplyOut(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    classification: Optional[str] = None
    sentiment: Optional[str] = None
    from_email: Optional[str] = None
    received_at: datetime
    company_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Import / Sync
# ═══════════════════════════════════════════════════════════════════════════════

class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[str] = []


class SyncResult(BaseModel):
    synced: int
    skipped: int


# ═══════════════════════════════════════════════════════════════════════════════
# Batch enrich
# ═══════════════════════════════════════════════════════════════════════════════

class BatchEnrichRequest(BaseModel):
    company_ids: List[uuid.UUID]


class EnrichResult(BaseModel):
    company_id: uuid.UUID
    status: str   # done | failed
    message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Suppression
# ═══════════════════════════════════════════════════════════════════════════════

class SuppressionEntryOut(BaseModel):
    id: uuid.UUID
    email: str
    reason: Optional[str] = None
    added_at: datetime

    model_config = {"from_attributes": True}
