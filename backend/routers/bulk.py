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
from backend.services.scraper import run_scraper, setup_google_sheets
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/bulk", tags=["bulk"])
logger = logging.getLogger(__name__)

automation_state = {
    "is_running": False,
    "current_stage": "idle",
    "target_leads": 0
}

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


async def run_enrich_all_task():
    """Background task: enrich all 'new' companies."""
    async with AsyncSessionLocal() as db:
        from backend.routers.enrich import _run_full_pipeline
        result = await db.execute(select(Company).where(Company.status == "new"))
        companies = result.scalars().all()
        logger.info(f"Enrich all: {len(companies)} companies.")
        for company in companies:
            try:
                await _run_full_pipeline(str(company.id), db)
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error(f"Enrich all failed for {company.name}: {exc}")


@router.post("/enrich-all")
async def start_enrich_all(background_tasks: BackgroundTasks):
    """Enrich all 'new' leads in the background."""
    background_tasks.add_task(run_enrich_all_task)
    return {"status": "started", "message": "Enrichment started for all new leads."}


async def run_send_all_task():
    """Background task: generate drafts and send for all 'enriched' companies."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Company).where(Company.status == "enriched")
        )
        companies = result.scalars().all()
        logger.info(f"Send all: {len(companies)} enriched companies.")
        for company in companies:
            try:
                draft_res = await generate_draft(str(company.id), db)
                if draft_res["status"] == "failed":
                    continue
                campaign_id = draft_res["campaign_id"]
                camp_res = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
                campaign = camp_res.scalar_one_or_none()
                if campaign:
                    campaign.status = "approved"
                    await db.commit()
                    send_res = await send_campaign(str(campaign_id), db)
                    if send_res["status"] == "failed":
                        campaign.status = "pending_review"
                        await db.commit()
                await asyncio.sleep(1)
            except Exception as exc:
                logger.error(f"Send all failed for {company.name}: {exc}")


@router.post("/send-all")
async def start_send_all(background_tasks: BackgroundTasks):
    """Generate drafts and send emails for all enriched leads."""
    background_tasks.add_task(run_send_all_task)
    return {"status": "started", "message": "Sending emails for all enriched leads in the background."}

class AutomateRequest(BaseModel):
    queries: List[str]
    target_leads: int
    timeout_minutes: Optional[int] = 10

def _run_scraper_sync(queries: List[str], target_leads: int, timeout_minutes: Optional[int]):
    """
    Run the scraper in a separate thread with its own event loop.
    Required on Windows because Playwright needs ProactorEventLoop to spawn
    browser subprocesses, but Uvicorn workers use SelectorEventLoop.
    """
    import sys
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scraper(queries, target_leads, timeout_minutes))
    except Exception as exc:
        logger.error("Scraper thread error in automation flow: %s", exc)
    finally:
        loop.close()

async def run_automate_task(request: AutomateRequest):
    """
    1. Scrape with timeout
    2. Enrich & Draft all new leads
    3. Approve & Send all pending campaigns
    4. Delete all leads from DB and clear Google Sheet
    """
    global automation_state
    automation_state["is_running"] = True
    automation_state["current_stage"] = "scraping"
    automation_state["target_leads"] = request.target_leads
    
    logger.info("Automation flow started.")
    
    # 1. Scrape
    try:
        await asyncio.to_thread(
            _run_scraper_sync, 
            request.queries, 
            request.target_leads, 
            request.timeout_minutes
        )
    except Exception as e:
        logger.error(f"Scraper error in automation flow: {e}")
    
    # 2. Bulk Enrich
    automation_state["current_stage"] = "enriching"
    logger.info("Automation flow: Starting enrichment...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.status == "new"))
        companies = result.scalars().all()
        for company in companies:
            try:
                await _run_full_pipeline(str(company.id), db)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Enrichment error for {company.name}: {e}")

    # 3. Bulk Draft
    automation_state["current_stage"] = "drafting"
    logger.info("Automation flow: Starting drafting...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Company).where(Company.status == "enriched"))
        companies = result.scalars().all()
        for company in companies:
            try:
                await generate_draft(str(company.id), db)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Drafting error for {company.name}: {e}")

    # 4. Bulk Send
    automation_state["current_stage"] = "sending"
    logger.info("Automation flow: Starting sending...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.status == "pending_review"))
        campaigns = result.scalars().all()
        for campaign in campaigns:
            try:
                campaign.status = "approved"
                await db.commit()
                send_res = await send_campaign(str(campaign.id), db)
                if send_res["status"] == "failed":
                    campaign.status = "pending_review"
                    await db.commit()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Send error for campaign {campaign.id}: {e}")

    # 5. Cleanup
    automation_state["current_stage"] = "cleanup"
    logger.info("Automation flow: Starting cleanup...")
    async with AsyncSessionLocal() as db:
        try:
            # This will cascade and delete contacts & campaigns as well.
            await db.execute(Company.__table__.delete())
            await db.commit()
            logger.info("Deleted all leads from the database.")
        except Exception as e:
            logger.error(f"Cleanup DB error: {e}")

    try:
        worksheet, _, _ = setup_google_sheets()
        if worksheet:
            # Delete all rows except the header
            all_values = worksheet.get_all_values()
            if len(all_values) > 1:
                # Need to use clear and re-insert header or delete rows
                worksheet.clear()
                worksheet.append_row(["Search Query", "Business Name", "Phone Number", "Email", "Website URL", "Address", "Google Maps URL"])
                logger.info("Cleared Google Sheet.")
    except Exception as e:
        logger.error(f"Cleanup Sheets error: {e}")

    logger.info("Automation flow completed successfully.")
    
    automation_state["is_running"] = False
    automation_state["current_stage"] = "idle"


@router.post("/automate")
async def start_automate(request: AutomateRequest, background_tasks: BackgroundTasks):
    """
    Runs the full end-to-end automated pipeline (Scrape -> Enrich -> Draft -> Send -> Cleanup).
    """
    if automation_state["is_running"]:
        return {"status": "error", "message": "Automation flow is already running."}
    
    background_tasks.add_task(run_automate_task, request)
    return {"status": "started", "message": "Full automated flow started in the background."}

from sqlalchemy import func

@router.get("/progress")
async def get_automation_progress(db: AsyncSession = Depends(get_db)):
    """
    Returns the real-time progress of the automation flow.
    """
    if not automation_state["is_running"]:
        return {
            "is_running": False,
            "current_stage": automation_state["current_stage"],
            "target_leads": automation_state["target_leads"],
            "leads_generated": 0,
            "emails_sent": 0
        }
    
    # Count leads generated
    res_leads = await db.execute(select(func.count(Company.id)))
    leads_generated = res_leads.scalar() or 0
    
    # Count emails sent
    res_emails = await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "sent"))
    emails_sent = res_emails.scalar() or 0
    
    return {
        "is_running": automation_state["is_running"],
        "current_stage": automation_state["current_stage"],
        "target_leads": automation_state["target_leads"],
        "leads_generated": leads_generated,
        "emails_sent": emails_sent
    }
