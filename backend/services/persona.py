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

    # Build evidence text from confirmed fields only — null fields are omitted
    evidence_parts = []
    if company.name:
        evidence_parts.append(f"Company name: {company.name}")
    if company.website:
        evidence_parts.append(f"Website: {company.website}")
    if company.industry:
        evidence_parts.append(f"Industry: {company.industry}")
    if company.employees_estimate:
        evidence_parts.append(f"Estimated employees: {company.employees_estimate}")
    if company.summary:
        evidence_parts.append(f"What they do: {company.summary}")
    if company.tech_stack_hints:
        evidence_parts.append(f"Technology stack hints: {company.tech_stack_hints}")
    if company.rag_rationale:
        evidence_parts.append(f"RAG opportunity note: {company.rag_rationale}")

    if not evidence_parts:
        return {"status": "failed", "message": "No enrichment data available for persona."}

    enrichment_text = "\n".join(evidence_parts)
    rag_score = company.rag_score or 0
    purchase_score = company.purchase_score or 0

    persona = llm.summarize_persona(enrichment_text, rag_score, purchase_score)

    if not persona:
        return {"status": "failed", "message": "LLM failed to generate persona summary."}

    company.persona_summary = persona
    await db.commit()

    return {"status": "done", "persona_summary": persona}
