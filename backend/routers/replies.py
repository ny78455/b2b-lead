"""
routers/replies.py — Inbound reply list

Endpoints:
  GET /api/replies  — List classified replies
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Reply, Campaign, Company
from backend.schemas import ReplyOut

router = APIRouter(prefix="/api/replies", tags=["replies"])


@router.get("", response_model=list[ReplyOut])
async def list_replies(
    classification: str | None = Query(None, description="Filter by classification"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List inbound classified replies."""
    query = (
        select(Reply)
        .order_by(Reply.received_at.desc())
        .options(selectinload(Reply.campaign).selectinload(Campaign.company))
    )

    if classification:
        query = query.where(Reply.classification == classification)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    replies = result.scalars().all()

    items = []
    for r in replies:
        items.append(
            ReplyOut(
                id=r.id,
                campaign_id=r.campaign_id,
                classification=r.classification,
                sentiment=r.sentiment,
                from_email=r.from_email,
                received_at=r.received_at,
                company_name=r.campaign.company.name if (r.campaign and r.campaign.company) else None,
            )
        )
    return items
