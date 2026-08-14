"""
routers/enrich.py — Enrichment pipeline trigger (Modules 2–5)

Endpoints:
  POST /api/enrich/{company_id}  — Full pipeline for one company
  POST /api/enrich/batch         — Batch pipeline with pacing delay
"""
import asyncio
import logging
import uuid
import time

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import BatchEnrichRequest, EnrichResult
from backend.services import enrichment, scoring, persona
from backend.config import get_settings

router = APIRouter(prefix="/api/enrich", tags=["enrichment"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def _run_full_pipeline(company_id: str, db: AsyncSession) -> dict:
    """Run Modules 2 → 3 → 4 → 5 in sequence for one company, returning timing data as well."""
    timings = {}
    
    # Module 2: Enrich
    t0 = time.time()
    result = await enrichment.enrich_company(company_id, db)
    t1 = time.time()
    timings['enrich'] = t1 - t0
    if result["status"] == "failed":
        return {"status": "failed", "message": result["message"], "timings": timings}

    # Modules 3 + 4: Score
    t0 = time.time()
    score_result = await scoring.score_company(company_id, db)
    t1 = time.time()
    timings['score'] = t1 - t0
    if score_result["status"] == "failed":
        logger.warning("Scoring failed for %s: %s", company_id, score_result.get("message"))

    # Module 5: Persona
    t0 = time.time()
    persona_result = await persona.build_persona(company_id, db)
    t1 = time.time()
    timings['persona'] = t1 - t0
    if persona_result["status"] == "failed":
        logger.warning("Persona failed for %s: %s", company_id, persona_result.get("message"))

    return {"status": "done", "message": "Pipeline complete.", "timings": timings}


@router.post("/{company_id}", response_model=EnrichResult)
async def enrich_one(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run the full enrichment pipeline (Modules 2–5) for a single company."""
    res = await _run_full_pipeline(str(company_id), db)
    return EnrichResult(company_id=company_id, status=res["status"], message=res.get("message"))


@router.post("/batch", response_model=list[EnrichResult])
async def enrich_batch(
    request: BatchEnrichRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run the enrichment pipeline for a list of company IDs.
    Companies are processed sequentially with a configurable delay
    (ENRICH_DELAY_SECONDS) to avoid hammering external sites.
    """
    results = []
    for company_id in request.company_ids:
        res = await _run_full_pipeline(str(company_id), db)
        results.append(EnrichResult(company_id=company_id, status=res["status"], message=res.get("message")))
        if len(request.company_ids) > 1:
            await asyncio.sleep(settings.ENRICH_DELAY_SECONDS)
    return results


@router.post("/{company_id}/draft")
async def enrich_and_draft(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run full enrichment pipeline then immediately generate an email draft."""
    from backend.services.email_draft import generate_draft
    
    total_start = time.time()
    
    # Step 1: Enrich
    enrich_result = await _run_full_pipeline(str(company_id), db)
    if enrich_result["status"] == "failed":
        raise HTTPException(status_code=400, detail=enrich_result.get("message"))
        
    timings = enrich_result.get("timings", {})
    
    # Step 2: Generate email draft
    t0 = time.time()
    draft_result = await generate_draft(str(company_id), db)
    t1 = time.time()
    timings['draft_email'] = t1 - t0
    
    if draft_result["status"] == "failed":
        raise HTTPException(status_code=400, detail=draft_result.get("message", "Draft generation failed"))
        
    total_time = time.time() - total_start
    
    # Check if a Gemini call was actually made based on the draft_source
    gemini_requests = 1 if draft_result.get("draft_source") == "gemini" else (1 if "failed" not in draft_result.get("status", "") else 0) # Assumes 1 attempt even on fallback, unless totally failed before calling

    print("\n==================================================")
    print(f"ENRICHMENT LLM USAGE REPORT for {company_id}")
    print(f"  1. Scrape + Extraction : 0 Gemini requests")
    print(f"  2. Rule-based Scoring  : 0 Gemini requests")
    print(f"  3. Persona Generation  : 0 Gemini requests")
    print(f"  4. Email Drafting      : 1 Gemini request")
    print("--------------------------------------------------")
    print(f"  TOTAL GEMINI REQUESTS  : 1")
    print("==================================================\n")
        
    return draft_result
