"""
services/scoring.py — Module 3 (RAG score) + Module 4 (purchase intent score)

Module 3 — Rule-based RAG opportunity score:
  Transparent weighted sum based on docs footprint, AI signals, compliance, etc.

Module 4 — Rule-based purchase intent score:
  Transparent weighted sum based on hiring roles, LLM tools, support focus, etc.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company

logger = logging.getLogger(__name__)

# ── Module 3 weight table (RAG Score) ─────────────────────────────────────────
RAG_SCORE_WEIGHTS = {
    "docs_heavy": 25,
    "ai_signals": 20,
    "compliance_industry": 20,
    "large_document_signals": 20,
    "support_team_signals": 15,
}

_DOCS_HEAVY_KEYWORDS = {"documentation", "knowledge base", "help center", "support portal",
                         "faq", "wiki", "knowledgebase", "customer support", "helpdesk"}
_HIGH_COMPLIANCE_INDUSTRIES = {"legal", "law", "finance", "financial", "banking", "insurance",
                                "healthcare", "medical", "pharma", "pharmaceutical", "compliance"}
_AI_SIGNAL_KEYWORDS = {"chatbot", "virtual assistant", "ai-powered", "ai assistant"}
_LARGE_DOC_KEYWORDS = {"resource library", "downloads", "manual", "whitepaper", "pdf guide"}
_SUPPORT_TEAM_KEYWORDS = {"support team", "customer success", "help desk", "customer care"}

def _compute_rag_score(company: Company) -> tuple[int, str]:
    text = (company.summary or "") + " " + (company.tech_stack_hints or "")
    text = text.lower()
    industry = (company.industry or "").lower()
    score = 0
    fired = []

    if any(kw in text for kw in _DOCS_HEAVY_KEYWORDS):
        score += RAG_SCORE_WEIGHTS["docs_heavy"]
        fired.append("docs-heavy")
    if any(kw in text for kw in _AI_SIGNAL_KEYWORDS):
        score += RAG_SCORE_WEIGHTS["ai_signals"]
        fired.append("existing AI signals")
    if any(kw in industry for kw in _HIGH_COMPLIANCE_INDUSTRIES):
        score += RAG_SCORE_WEIGHTS["compliance_industry"]
        fired.append("compliance-heavy industry")
    if any(kw in text for kw in _LARGE_DOC_KEYWORDS):
        score += RAG_SCORE_WEIGHTS["large_document_signals"]
        fired.append("large document footprint")
    if any(kw in text for kw in _SUPPORT_TEAM_KEYWORDS):
        score += RAG_SCORE_WEIGHTS["support_team_signals"]
        fired.append("dedicated support team")

    rationale = f"Matched signals: {', '.join(fired)}." if fired else "No strong RAG-fit signals detected in scraped text."
    return min(score, 100), rationale


# ── Module 4 weight table (Purchase Score) ────────────────────────────────────
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

_AI_HIRING_KEYWORDS = {"ai", "machine learning", "llm", "nlp", "ml engineer", "data scientist"}
_LLM_TOOL_KEYWORDS = {"openai", "langchain", "hugging face", "huggingface", "cohere", "anthropic",
                       "llama", "gemini", "gpt", "vector", "embedding", "rag"}
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
    Run Module 3 (RAG score) and Module 4 (purchase score) for a single company.
    Company must already be enriched.
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    if company.enrichment_status != "done":
        return {"status": "failed", "message": "Company not yet enriched."}

    # ── Module 3: RAG score (Rule-based) ──────────────────────────────────────
    rag_score, rag_rationale = _compute_rag_score(company)
    company.rag_score = rag_score
    company.rag_rationale = rag_rationale

    # ── Module 4: Purchase intent score (transparent rule-based) ──────────────
    company.purchase_score = _compute_purchase_score(company)

    await db.commit()
    return {
        "status": "done",
        "rag_score": company.rag_score,
        "purchase_score": company.purchase_score,
    }
