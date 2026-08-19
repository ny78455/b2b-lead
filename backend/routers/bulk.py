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

BATCH_SIZE = 50  # leads per scrape → enrich → send cycle

async def run_automate_task(request: AutomateRequest):
    """
    Batched pipeline — repeats until target_leads are processed:
      1. Scrape BATCH_SIZE leads
      2. Enrich & Draft those leads
      3. Approve & Send their campaigns
      4. Cleanup batch from DB / Sheet
    After all batches are done, do a final cleanup pass.
    """
    global automation_state
    automation_state["is_running"] = True
    automation_state["current_stage"] = "scraping"
    automation_state["target_leads"] = request.target_leads

    logger.info(
        "Automation flow started — target %d leads in batches of %d.",
        request.target_leads,
        BATCH_SIZE,
    )

    total_sent = 0
    remaining = request.target_leads

    while remaining > 0:
        batch_size = min(BATCH_SIZE, remaining)
        logger.info(
            "=== Batch start: scraping %d leads (total sent so far: %d) ===",
            batch_size,
            total_sent,
        )

        # ── Step 1: Scrape one batch ──────────────────────────────────────────
        automation_state["current_stage"] = "scraping"
        try:
            await asyncio.to_thread(
                _run_scraper_sync,
                request.queries,
                batch_size,
                None,  # no timeout — scrape exactly batch_size leads
            )
        except Exception as e:
            logger.error("Scraper error in automation batch: %s", e)

        # ── Step 2: Enrich all 'new' companies from this batch ────────────────
        automation_state["current_stage"] = "enriching"
        logger.info("Batch: starting enrichment…")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Company).where(Company.status == "new"))
            companies = result.scalars().all()
            logger.info("Batch: %d companies to enrich.", len(companies))
            for company in companies:
                try:
                    await _run_full_pipeline(str(company.id), db)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error("Enrichment error for %s: %s", company.name, e)

        # ── Step 3: Draft all 'enriched' companies ────────────────────────────
        automation_state["current_stage"] = "drafting"
        logger.info("Batch: starting drafting…")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Company).where(Company.status == "enriched"))
            companies = result.scalars().all()
            logger.info("Batch: %d companies to draft.", len(companies))
            for company in companies:
                try:
                    await generate_draft(str(company.id), db)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error("Drafting error for %s: %s", company.name, e)

        # ── Step 4: Approve & Send all pending campaigns ──────────────────────
        automation_state["current_stage"] = "sending"
        logger.info("Batch: starting sending…")
        batch_sent = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Campaign).where(Campaign.status == "pending_review")
            )
            campaigns = result.scalars().all()
            logger.info("Batch: %d campaigns to send.", len(campaigns))
            for campaign in campaigns:
                try:
                    campaign.status = "approved"
                    await db.commit()
                    send_res = await send_campaign(str(campaign.id), db)
                    if send_res["status"] == "failed":
                        logger.error(
                            "Send failed for campaign %s: %s",
                            campaign.id,
                            send_res.get("message"),
                        )
                        campaign.status = "pending_review"
                        await db.commit()
                    else:
                        batch_sent += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error("Send error for campaign %s: %s", campaign.id, e)

        total_sent += batch_sent
        remaining -= batch_sent
        logger.info(
            "=== Batch done: sent %d, total sent %d, remaining %d ===",
            batch_sent,
            total_sent,
            remaining,
        )

        # ── Step 5: Cleanup this batch from DB & Google Sheet ─────────────────
        automation_state["current_stage"] = "cleanup"
        logger.info("Batch: cleaning up…")
        async with AsyncSessionLocal() as db:
            try:
                await db.execute(Company.__table__.delete())
                await db.commit()
                logger.info("Batch: deleted all leads from the database.")
            except Exception as e:
                logger.error("Batch cleanup DB error: %s", e)

        try:
            worksheet, _, _ = setup_google_sheets()
            if worksheet:
                all_values = worksheet.get_all_values()
                if len(all_values) > 1:
                    worksheet.clear()
                    worksheet.append_row(
                        ["Search Query", "Business Name", "Phone Number",
                         "Email", "Website URL", "Address", "Google Maps URL"]
                    )
                    logger.info("Batch: cleared Google Sheet.")
        except Exception as e:
            logger.error("Batch cleanup Sheets error: %s", e)

        # Safety: if no emails were sent in this batch (all failed/blocked),
        # break to avoid an infinite loop.
        if batch_sent == 0:
            logger.warning(
                "No emails sent in this batch — stopping to avoid an infinite loop."
            )
            break

    logger.info(
        "Automation flow completed. Total emails sent: %d / %d requested.",
        total_sent,
        request.target_leads,
    )
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
