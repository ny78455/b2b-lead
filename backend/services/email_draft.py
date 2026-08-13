"""
services/email_draft.py — Module 6: Email Draft Generation

Creates an HTML email draft for a company and stores it in the campaigns table
with status = 'pending_review'. No email is sent here — a human must approve.
"""
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.models import Campaign, Company, Contact
from backend.services import llm
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_draft(company_id: str, db: AsyncSession) -> dict:
    """
    Generate an HTML email draft for a company and save it as a pending campaign.
    Requires persona_summary to be populated (run enrichment pipeline first).
    Returns the created campaign ID.
    """
    # Fetch company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    if not company.persona_summary:
        return {"status": "failed", "message": "Persona summary not yet generated. Run enrichment first."}

    # Find primary contact (first available)
    contact_result = await db.execute(
        select(Contact)
        .where(Contact.company_id == company_id)
        .limit(1)
    )
    contact = contact_result.scalar_one_or_none()
    contact_name = contact.name if (contact and contact.name) else "there"

    # Use static Google Calendar link from config
    meeting_link = settings.CALENDAR_LINK

    # Call LLM to generate draft
    draft_html = llm.draft_email(
        persona_summary=company.persona_summary,
        company_name=company.name,
        contact_name=contact_name,
        sender_name=settings.SENDER_NAME,
        sender_company=settings.SENDER_COMPANY,
        meeting_link=meeting_link,
        website="https://www.vantrade.online/",
    )

    if not draft_html:
        return {"status": "failed", "message": "LLM failed to generate email draft."}

    # Ensure draft is a proper HTML document with a white background so it's visible in dark mode
    if not draft_html.strip().lower().startswith("<html"):
        draft_html = draft_html.replace('\n', '<br>')
        draft_html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; background-color: #ffffff; padding: 20px; margin: 0; }}
</style>
</head>
<body>
{draft_html}
</body>
</html>"""

    # Generate a subject line (derive from company name + angle)
    subject = f"Quick question about {company.name}'s knowledge workflow"

    # Create campaign record
    campaign = Campaign(
        company_id=company.id,
        contact_id=contact.id if contact else None,
        subject=subject,
        draft_html=draft_html,
        status="pending_review",
    )
    db.add(campaign)

    # Update company status
    company.status = "drafted"

    await db.commit()
    await db.refresh(campaign)

    return {
        "status": "done",
        "campaign_id": str(campaign.id),
        "subject": subject,
    }
