import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List

from backend.services.scraper import run_scraper

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)

class ScrapeRequest(BaseModel):
    queries: List[str]

@router.post("")
async def start_scraping(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Starts a background task to scrape Google Maps for the provided queries.
    Results will be added to Google Sheets and synced to the database.
    """
    if not request.queries:
        raise HTTPException(status_code=400, detail="At least one query is required.")
        
    # Schedule the scraper to run in the background
    background_tasks.add_task(run_scraper, request.queries)
    
    return {"status": "started", "message": f"Scraping started in the background for {len(request.queries)} queries."}
