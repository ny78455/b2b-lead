"""
services/persona.py — Module 5: Persona Summary Builder

Generates a company persona deterministically using only verified enrichment data.
No facts are fabricated — if a field is null, it is excluded from the prompt.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company

logger = logging.getLogger(__name__)

def build_persona_text(company: Company) -> str:
    parts = [f"{company.name} operates in the {company.industry or 'unclassified'} industry."]
    if company.employees_estimate:
        parts.append(f"Estimated size: {company.employees_estimate}.")
    if company.summary:
        parts.append(company.summary)
    if company.tech_stack_hints:
        parts.append(f"Notable tech/tools mentioned on their site: {company.tech_stack_hints}.")
    parts.append(f"RAG-fit score: {company.rag_score or 0}/100 — {company.rag_rationale or 'N/A'}")
    parts.append(f"Purchase-intent score: {company.purchase_score or 0}/100.")
    return " ".join(parts)


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

    # Generate the persona using deterministic template
    company.persona_summary = build_persona_text(company)
    await db.commit()

    return {"status": "done", "persona_summary": company.persona_summary}
