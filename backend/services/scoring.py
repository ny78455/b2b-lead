"""
services/scoring.py — Module 3 (RAG score) + Module 4 (purchase intent score)

Module 3 — LLM-based RAG opportunity score:
  Single Gemma call → 0-100 score + 1-sentence rationale.

Module 4 — Rule-based purchase intent score:
  Transparent weighted sum. Weights are documented here so they're easy to tune.
  This is intentionally NOT a black box.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company
from backend.services import llm

logger = logging.getLogger(__name__)


# ── Module 4 weight table ─────────────────────────────────────────────────────
# Tune these values here. Total possible = 100.
PURCHASE_SCORE_WEIGHTS = {
    # +20 if job postings / tech_stack_hints signal AI/ML hiring
    "hiring_ai_role": 20,
    # +20 if the RAG opportunity score itself is high (≥ 70)
    "rag_score_high": 20,
    # +15 if tech stack explicitly mentions LLM tools
    "tech_stack_llm": 15,
    # +15 if summary signals support-heavy or docs-heavy operations
    "support_or_docs_heavy": 15,
    # +15 if employee estimate falls in the SMB target range (5-500)
    "company_size_target": 15,
    # +15 if industry is compliance-heavy (legal, medical, financial, insurance)
    "high_compliance_industry": 15,
}

# Keywords for each signal (all lowercased for comparison)
_AI_HIRING_KEYWORDS = {"ai", "machine learning", "llm", "nlp", "ml engineer", "data scientist"}
_LLM_TOOL_KEYWORDS = {"openai", "langchain", "hugging face", "huggingface", "cohere", "anthropic",
                       "llama", "gemini", "gpt", "vector", "embedding", "rag"}
_DOCS_HEAVY_KEYWORDS = {"documentation", "knowledge base", "help center", "support portal",
                         "faq", "wiki", "knowledgebase", "customer support", "helpdesk"}
_HIGH_COMPLIANCE_INDUSTRIES = {"legal", "law", "finance", "financial", "banking", "insurance",
                                "healthcare", "medical", "pharma", "pharmaceutical", "compliance"}
_SMB_EMPLOYEE_RANGES = {"1-10", "11-50", "51-200", "201-500"}


def _compute_purchase_score(company: Company) -> int:
    """
    Transparent, inspectable weighted rule score.
    Each signal is checked against the enrichment fields and the rag_score.
    Maximum possible: 100 (all signals fire).
    """
    score = 0
    tech = (company.tech_stack_hints or "").lower()
    summary = (company.summary or "").lower()
    industry = (company.industry or "").lower()
    employees = (company.employees_estimate or "").lower()
    rag = company.rag_score or 0

    # Signal: AI/ML hiring detected in tech stack hints
    if any(kw in tech for kw in _AI_HIRING_KEYWORDS):
        score += PURCHASE_SCORE_WEIGHTS["hiring_ai_role"]

    # Signal: RAG score is high (≥ 70)
    if rag >= 70:
        score += PURCHASE_SCORE_WEIGHTS["rag_score_high"]

    # Signal: Tech stack mentions LLM tools
    if any(kw in tech for kw in _LLM_TOOL_KEYWORDS):
        score += PURCHASE_SCORE_WEIGHTS["tech_stack_llm"]

    # Signal: Company is support- or docs-heavy
    if any(kw in summary for kw in _DOCS_HEAVY_KEYWORDS):
        score += PURCHASE_SCORE_WEIGHTS["support_or_docs_heavy"]

    # Signal: Company size in SMB target range (5-500 employees)
    if any(r in employees for r in _SMB_EMPLOYEE_RANGES):
        score += PURCHASE_SCORE_WEIGHTS["company_size_target"]

    # Signal: High-compliance industry
    if any(kw in industry for kw in _HIGH_COMPLIANCE_INDUSTRIES):
        score += PURCHASE_SCORE_WEIGHTS["high_compliance_industry"]

    return min(score, 100)   # cap at 100


# ── Public interface ──────────────────────────────────────────────────────────

async def score_company(company_id: str, db: AsyncSession) -> dict:
    """
    Run Module 3 (LLM RAG score) and Module 4 (rule-based purchase score)
    for a single company. Company must already be enriched.
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    if company.enrichment_status != "done":
        return {"status": "failed", "message": "Company not yet enriched."}

    # Build enrichment text for the LLM
    enrichment_text = "\n".join(filter(None, [
        f"Industry: {company.industry}",
        f"Employees: {company.employees_estimate}",
        f"Summary: {company.summary}",
        f"Tech stack hints: {company.tech_stack_hints}",
    ]))

    # ── Module 3: RAG score (LLM) ─────────────────────────────────────────────
    rag_result = llm.score_rag(enrichment_text)
    if rag_result:
        company.rag_score = int(rag_result.get("score", 0))
        company.rag_rationale = rag_result.get("rationale")
    else:
        logger.warning("RAG scoring failed for company %s — leaving null.", company_id)

    # ── Module 4: Purchase intent score (transparent rule-based) ──────────────
    company.purchase_score = _compute_purchase_score(company)

    await db.commit()
    return {
        "status": "done",
        "rag_score": company.rag_score,
        "purchase_score": company.purchase_score,
    }
