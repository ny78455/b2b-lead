"""
services/persona.py — Module 5: Persona Summary Builder

Generates a 3-5 sentence company persona using only verified enrichment data.
No facts are fabricated — if a field is null, it is excluded from the prompt.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company
from backend.services import llm

logger = logging.getLogger(__name__)


async def build_persona(company_id: str, db: AsyncSession) -> dict:
    """
    Build a persona summary for a company and persist it.
    Requires enrichment_status == 'done' and rag_score / purchase_score to be set.
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    if company.enrichment_status != "done":
        return {"status": "failed", "message": "Company not yet enriched."}

    # Persona summary is now generated during the unified Module 2 extraction step.
    if not company.persona_summary:
        return {"status": "failed", "message": "Persona summary was not populated during enrichment."}

    return {"status": "done", "persona_summary": company.persona_summary}
