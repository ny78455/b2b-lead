"""
routers/sync.py — Google Sheet to Postgres sync

Reads the staging Google Sheet outputted by Module 1, maps columns,
and upserts into Postgres (companies + contacts).
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import Company, Contact
from backend.schemas import SyncResult
from backend.config import get_settings
from backend.routers.leads import _map_row

import gspread

router = APIRouter(prefix="/api", tags=["sync"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.post("/sync-sheet", response_model=SyncResult)
async def sync_sheet(
    db: AsyncSession = Depends(get_db),
):
    """
    Connect to Google Sheets, read all rows, and upsert any new leads
    into the Postgres database. Skips rows where the email is already in the DB.
    """
    try:
        gc = gspread.service_account(filename=settings.GSPREAD_CREDENTIALS_FILE)
        sh = gc.open(settings.SPREADSHEET_NAME)
        worksheet = sh.sheet1
        all_values = worksheet.get_all_values()
    except Exception as exc:
        logger.error("Failed to read Google Sheet: %s", exc)
        return SyncResult(synced=0, skipped=0)

    if not all_values or len(all_values) < 2:
        return SyncResult(synced=0, skipped=0)

    headers = all_values[0]
    synced = 0
    skipped = 0

    for row_list in all_values[1:]:
        # pad row if it's shorter than headers
        row_list += [""] * (len(headers) - len(row_list))
        row = dict(zip(headers, row_list))
        fields = _map_row(headers, row)

        company_name = fields.get("name", "").strip()
        email_val = fields.get("email", "").strip().lower()

        if not company_name or not email_val or email_val == "n/a":
            skipped += 1
            continue

        # Skip if email already exists
        existing = await db.execute(select(Contact).where(Contact.email == email_val))
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Create company
        company = Company(
            name=company_name,
            website=fields.get("website") or None,
            phone=fields.get("phone") or None,
            address=fields.get("address") or None,
            google_maps_url=fields.get("google_maps_url") or None,
            search_query=fields.get("search_query") or None,
            enrichment_status="pending",
            status="new",
        )
        db.add(company)
        await db.flush()

        # Create contact
        contact = Contact(
            company_id=company.id,
            email=email_val,
            source="sheet_sync",
            confidence="medium",
        )
        db.add(contact)
        synced += 1

    await db.commit()
    return SyncResult(synced=synced, skipped=skipped)
