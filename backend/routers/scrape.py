import sys
import asyncio
import threading
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from backend.services.scraper import run_scraper
import backend.services.scraper as scraper_service

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)


class ScrapeRequest(BaseModel):
    queries: List[str]


def _run_scraper_in_thread(queries: List[str]):
    """
    Run the scraper in a separate thread with its own event loop.
    This is required on Windows because Playwright needs ProactorEventLoop
    to spawn browser subprocesses, but Uvicorn workers use SelectorEventLoop.
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scraper(queries))
    except Exception as exc:
        logger.error("Scraper thread error: %s", exc)
    finally:
        loop.close()


@router.post("")
async def start_scraping(request: ScrapeRequest):
    """
    Starts the Google Maps scraper in a background thread for the provided queries.
    Results will be added to Google Sheets and synced to the database.
    """
    if not request.queries:
        raise HTTPException(status_code=400, detail="At least one query is required.")

    # Launch in a daemon thread with its own ProactorEventLoop (Windows-safe)
    thread = threading.Thread(
        target=_run_scraper_in_thread,
        args=(request.queries,),
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "message": f"Scraping started in the background for {len(request.queries)} queries.",
    }

@router.post("/stop")
async def stop_scraping():
    """
    Sets the STOP_SCRAPING flag to halt the background scraper.
    """
    scraper_service.STOP_SCRAPING = True
    return {"status": "stopped", "message": "Scraping halt signal sent. The scraper will stop shortly."}
