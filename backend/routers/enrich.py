"""
routers/enrich.py — Enrichment pipeline trigger (Modules 2–5)

Endpoints:
  POST /api/enrich/{company_id}  — Full pipeline for one company
  POST /api/enrich/batch         — Batch pipeline with pacing delay
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas import BatchEnrichRequest, EnrichResult
from backend.services import enrichment, scoring, persona
from backend.config import get_settings

router = APIRouter(prefix="/api/enrich", tags=["enrichment"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def _run_full_pipeline(company_id: str, db: AsyncSession) -> EnrichResult:
    """Run Modules 2 → 3 → 4 → 5 in sequence for one company."""
    # Module 2: Enrich
    result = await enrichment.enrich_company(company_id, db)
    if result["status"] == "failed":
        return EnrichResult(company_id=company_id, status="failed", message=result["message"])

    # Modules 3 + 4: Score
    score_result = await scoring.score_company(company_id, db)
    if score_result["status"] == "failed":
        logger.warning("Scoring failed for %s: %s", company_id, score_result.get("message"))

    # Module 5: Persona
    persona_result = await persona.build_persona(company_id, db)
    if persona_result["status"] == "failed":
        logger.warning("Persona failed for %s: %s", company_id, persona_result.get("message"))

    return EnrichResult(company_id=company_id, status="done", message="Pipeline complete.")


@router.post("/{company_id}", response_model=EnrichResult)
async def enrich_one(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run the full enrichment pipeline (Modules 2–5) for a single company."""
    return await _run_full_pipeline(str(company_id), db)


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
        result = await _run_full_pipeline(str(company_id), db)
        results.append(result)
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
    # Step 1: Enrich
    enrich_result = await _run_full_pipeline(str(company_id), db)
    if enrich_result.status == "failed":
        raise HTTPException(status_code=400, detail=enrich_result.message)
    # Step 2: Generate email draft
    draft_result = await generate_draft(str(company_id), db)
    if draft_result["status"] == "failed":
        raise HTTPException(status_code=400, detail=draft_result.get("message", "Draft generation failed"))
    return draft_result
