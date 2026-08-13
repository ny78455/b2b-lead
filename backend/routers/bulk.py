import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db, AsyncSessionLocal
from backend.models import Company, Campaign
from backend.routers.enrich import _run_full_pipeline
from backend.services.email_draft import generate_draft
from backend.services.sender import send_campaign

router = APIRouter(prefix="/api/bulk", tags=["bulk"])
logger = logging.getLogger(__name__)

async def run_bulk_send_task():
    """Background task to automate enriching, drafting, and sending emails."""
    async with AsyncSessionLocal() as db:
        # Find companies that have not been drafted or sent yet
        result = await db.execute(
            select(Company)
            .where(Company.status.in_(["new", "enriched"]))
            .limit(10) # limit batch size for safety
        )
        companies = result.scalars().all()
        
        logger.info(f"Found {len(companies)} companies for bulk send.")

        for company in companies:
            logger.info(f"Processing company: {company.name}")
            # 1. Enrich if needed
            if company.status == "new" or not company.persona_summary:
                enrich_res = await _run_full_pipeline(str(company.id), db)
                if enrich_res.status == "failed":
                    logger.warning(f"Enrichment failed for {company.name}, skipping.")
                    continue
            
            # 2. Draft using LLM
            draft_res = await generate_draft(str(company.id), db)
            if draft_res["status"] == "failed":
                logger.warning(f"Drafting failed for {company.name}: {draft_res.get('message')}")
                continue
                
            campaign_id = draft_res["campaign_id"]
            
            # 3. Approve and Send (bypass manual review)
            camp_res = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
            campaign = camp_res.scalar_one_or_none()
            if campaign:
                campaign.status = "approved"
                await db.commit()
                
                send_res = await send_campaign(str(campaign_id), db)
                if send_res["status"] == "failed":
                    logger.error(f"Failed to send email to {company.name}: {send_res.get('message')}")
                    # revert status
                    campaign.status = "pending_review"
                    await db.commit()
                else:
                    logger.info(f"Successfully sent email to {company.name}")

@router.post("/send")
async def start_bulk_send(background_tasks: BackgroundTasks):
    """
    Starts a background task to generate drafts and send them immediately
    for all pending new/enriched leads.
    """
    background_tasks.add_task(run_bulk_send_task)
    return {"status": "started", "message": "Bulk mailing pipeline started in the background."}
