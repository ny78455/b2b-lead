"""
routers/leads.py — Lead import and CRM list view

Endpoints:
  POST /api/leads/import-csv  — CSV upload → companies + contacts
  GET  /api/leads             — Paginated CRM table data
  POST /api/leads/unsubscribe — Handle unsubscribe link clicks (compliance)
"""
import csv
import io
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from backend.database import get_db
from backend.models import Company, Contact, SuppressionEntry
from backend.schemas import CompanyListItem, ContactOut, ImportResult, SuppressionEntryOut
from backend.services.suppression import add_to_suppression
from backend.services.sender import verify_unsubscribe_token

router = APIRouter(prefix="/api/leads", tags=["leads"])
logger = logging.getLogger(__name__)

# Expected CSV columns from the Google Sheet export
# "Search Query,Business Name,Phone Number,Email,Website URL,Address,Google Maps URL,Date Scraped"
_COL_MAP = {
    "search_query": ["search query", "query"],
    "name": ["business name", "name", "company name"],
    "phone": ["phone number", "phone"],
    "email": ["email"],
    "website": ["website url", "website"],
    "address": ["address"],
    "google_maps_url": ["google maps url", "maps url"],
}


def _map_row(header: list[str], row: dict) -> dict:
    """Map CSV row (case-insensitive) to our field names."""
    normalised = {k.strip().lower(): v.strip() for k, v in row.items()}
    result = {}
    for field, aliases in _COL_MAP.items():
        for alias in aliases:
            if alias in normalised and normalised[alias]:
                result[field] = normalised[alias]
                break
    return result


@router.post("/import-csv", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CSV file exported from the Google Sheet (or any CSV matching
    the column names). Creates Company + Contact records; skips duplicates
    by website URL or email.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            fields = _map_row(list(row.keys()), row)

            company_name = fields.get("name", "").strip()
            if not company_name:
                skipped += 1
                continue

            email_val = fields.get("email", "").strip().lower()
            website_val = fields.get("website", "").strip()

            # Dedup: skip if email already exists in contacts
            if email_val:
                existing = await db.execute(
                    select(Contact).where(Contact.email == email_val)
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

            # Create company
            company = Company(
                name=company_name,
                website=website_val or None,
                phone=fields.get("phone") or None,
                address=fields.get("address") or None,
                google_maps_url=fields.get("google_maps_url") or None,
                search_query=fields.get("search_query") or None,
                enrichment_status="pending",
                status="new",
            )
            db.add(company)
            await db.flush()  # get company.id

            # Create contact if email found
            if email_val:
                contact = Contact(
                    company_id=company.id,
                    email=email_val,
                    source="csv_import",
                    confidence="medium",
                )
                db.add(contact)

            imported += 1

        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            skipped += 1

    await db.commit()
    return ImportResult(imported=imported, skipped=skipped, errors=errors)


@router.get("", response_model=list[CompanyListItem])
async def list_leads(
    status: Optional[str] = Query(None, description="Filter by status: new|enriched|drafted|sent"),
    search: Optional[str] = Query(None, description="Search by company name or website"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated company list for the CRM dashboard."""
    query = select(Company).order_by(Company.updated_at.desc())

    if status:
        query = query.where(Company.status == status)

    if search:
        like = f"%{search}%"
        query = query.where(
            or_(Company.name.ilike(like), Company.website.ilike(like))
        )

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    companies = result.scalars().all()

    # Attach primary contact email for display
    items = []
    for c in companies:
        contact_result = await db.execute(
            select(Contact).where(Contact.company_id == c.id).limit(1)
        )
        contact = contact_result.scalar_one_or_none()
        items.append(
            CompanyListItem(
                id=c.id,
                name=c.name,
                website=c.website,
                industry=c.industry,
                rag_score=c.rag_score,
                purchase_score=c.purchase_score,
                enrichment_status=c.enrichment_status,
                status=c.status,
                email=contact.email if contact else None,
                updated_at=c.updated_at,
            )
        )
    return items

@router.delete("/{company_id}")
async def delete_lead(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a company and its associated contacts."""
    result = await db.execute(select(Company).where(Company.id == str(company_id)))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    await db.delete(company)
    await db.commit()
    return {"status": "deleted"}


@router.delete("")
async def delete_all_leads(
    db: AsyncSession = Depends(get_db),
):
    """Delete ALL companies and their associated records."""
    result = await db.execute(select(Company))
    companies = result.scalars().all()
    for company in companies:
        await db.delete(company)
    await db.commit()
    return {"status": "deleted", "count": len(companies)}


# ── Unsubscribe endpoint (compliance) ─────────────────────────────────────────

@router.get("/unsubscribe")
async def handle_unsubscribe(
    campaign_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Processes an unsubscribe link click.
    Verifies the HMAC token, adds the contact email to the suppression list.
    Returns a simple confirmation page.
    """
    if not verify_unsubscribe_token(campaign_id, token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token.")

    from backend.models import Campaign, Contact
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign or not campaign.contact_id:
        return {"message": "You have been unsubscribed."}

    contact_result = await db.execute(select(Contact).where(Contact.id == campaign.contact_id))
    contact = contact_result.scalar_one_or_none()
    if contact:
        await add_to_suppression(contact.email, "unsubscribe", db)

    return {"message": "You have been successfully unsubscribed. You will receive no further emails."}
