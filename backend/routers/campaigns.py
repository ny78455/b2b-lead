"""
routers/campaigns.py — Email draft lifecycle (Modules 6, 7, 8)

Endpoints:
  POST /api/campaigns/draft/{company_id}  — Generate draft (Module 6)
  GET  /api/campaigns/pending             — Review queue (Module 7)
  GET  /api/campaigns/{id}               — Single campaign detail
  PUT  /api/campaigns/{id}/approve        — Approve & Send (Module 8)
  PUT  /api/campaigns/{id}/reject         — Reject draft
  PUT  /api/campaigns/{id}/edit           — Edit draft HTML
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Campaign, Company, Contact, Reply
from backend.schemas import CampaignOut, CampaignEditRequest, CampaignPendingItem
from backend.services.email_draft import generate_draft
from backend.services.sender import send_campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])
logger = logging.getLogger(__name__)


@router.post("/draft/{company_id}")
async def create_draft(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Generate a pending email draft for a company (Module 6)."""
    result = await generate_draft(str(company_id), db)
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/pending", response_model=list[CampaignPendingItem])
async def list_pending(
    db: AsyncSession = Depends(get_db),
):
    """Return all campaigns awaiting human review."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.status == "pending_review")
        .order_by(Campaign.created_at.desc())
        .options(selectinload(Campaign.company), selectinload(Campaign.contact))
    )
    campaigns = result.scalars().all()

    items = []
    for c in campaigns:
        items.append(
            CampaignPendingItem(
                id=c.id,
                company_name=c.company.name if c.company else "Unknown",
                contact_email=c.contact.email if c.contact else None,
                subject=c.subject,
                rag_score=c.company.rag_score if c.company else None,
                purchase_score=c.company.purchase_score if c.company else None,
                created_at=c.created_at,
            )
        )
    return items


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return full campaign detail including draft HTML and company info."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.company).selectinload(Company.contacts))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


@router.put("/{campaign_id}/approve")
async def approve_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Human approval gate — sets status to 'approved' then immediately sends.
    No email is ever sent without this explicit human action.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is '{campaign.status}' — only pending_review campaigns can be approved.",
        )

    # Set to approved before sending
    campaign.status = "approved"
    await db.commit()

    # Send via Module 8
    send_result = await send_campaign(str(campaign_id), db)
    if send_result["status"] == "failed":
        # Roll back approval on send failure so the human can retry
        campaign.status = "pending_review"
        await db.commit()
        raise HTTPException(status_code=500, detail=send_result["message"])

    return send_result


@router.put("/{campaign_id}/reject")
async def reject_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending draft."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    campaign.status = "rejected"
    await db.commit()
    return {"status": "rejected", "campaign_id": str(campaign_id)}


@router.put("/{campaign_id}/edit")
async def edit_campaign(
    campaign_id: uuid.UUID,
    body: CampaignEditRequest,
    db: AsyncSession = Depends(get_db),
):
    """Edit the draft HTML (and optionally subject) of a pending campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.status not in ("pending_review",):
        raise HTTPException(status_code=400, detail="Only pending campaigns can be edited.")

    campaign.draft_html = body.draft_html
    if body.subject:
        campaign.subject = body.subject
    await db.commit()
    return {"status": "updated", "campaign_id": str(campaign_id)}
