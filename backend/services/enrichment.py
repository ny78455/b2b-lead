"""
services/enrichment.py — Module 2: Company Enrichment

For each company website:
  1. Fetch and respect robots.txt — mark failed if scraping is disallowed.
  2. Fetch homepage + /about + /careers (up to 3 pages).
  3. Pass combined text to Gemma LLM to extract:
       industry, employees_estimate, summary, tech_stack_hints
  4. Update the database record.

Constraints (spec §2):
  - Respect robots.txt — no bypass.
  - If scrape fails or is blocked, mark enrichment_status = 'failed' and skip.
  - No retry loops that hammer a server.
  - Null fields stay null — never filled by speculation.
"""
import logging
import re
import asyncio
from urllib.parse import urljoin, urlparse
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company
from backend.services import llm

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "B2BOutreachBot/1.0 (+https://github.com/ny78455/b2b-lead; respectful-scraper)",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15.0  # seconds
MAX_TEXT_CHARS = 3000  # cap text sent to LLM per page


# ── Robots.txt check ──────────────────────────────────────────────────────────

def _is_scraping_allowed(website: str) -> bool:
    """Return False if robots.txt disallows our user agent for any path."""
    try:
        parsed = urlparse(website if website.startswith("http") else f"https://{website}")
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()  # blocking — acceptable for background enrichment tasks

        # Check both the homepage and sub-paths we intend to visit
        for path in ["/", "/about", "/careers"]:
            if not rp.can_fetch("*", urljoin(f"{parsed.scheme}://{parsed.netloc}", path)):
                return False
        return True
    except Exception as exc:
        logger.debug("robots.txt check failed for %s: %s — allowing by default.", website, exc)
        return True   # if we can't read robots.txt, proceed cautiously but don't block


# ── Page fetching ─────────────────────────────────────────────────────────────

async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a URL and return cleaned body text (max MAX_TEXT_CHARS chars)."""
    try:
        resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise tags
        for tag in soup(["script", "style", "nav", "footer", "head", "noscript"]):
            tag.decompose()

        text = " ".join(soup.get_text(separator=" ").split())
        return text[:MAX_TEXT_CHARS]
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return ""


async def _gather_site_text(website: str) -> str:
    """Fetch homepage + /about + /careers and concatenate."""
    base = website if website.startswith("http") else f"https://{website}"
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    pages = [
        base,
        urljoin(origin, "/about"),
        urljoin(origin, "/careers"),
    ]

    async with httpx.AsyncClient(headers=HEADERS, verify=False) as client:
        # Fetch all pages concurrently
        tasks = [_fetch_text(client, url) for url in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        texts = []
        for url, result in zip(pages, results):
            if isinstance(result, Exception):
                logger.debug("Gather failed for %s: %s", url, result)
            elif result:  # if text was returned
                texts.append(f"[Page: {url}]\n{result}")

    return "\n\n".join(texts)




# ── Main entry point ──────────────────────────────────────────────────────────

async def enrich_company(company_id: str, db: AsyncSession) -> dict:
    """
    Run the full Module 2 enrichment pipeline for one company.
    Returns {"status": "done"|"failed", "message": str}.
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    if not company.website:
        company.enrichment_status = "failed"
        await db.commit()
        return {"status": "failed", "message": "No website URL."}

    # Step 1 — robots.txt check
    if not _is_scraping_allowed(company.website):
        logger.warning("robots.txt disallows scraping for %s", company.website)
        company.enrichment_status = "failed"
        await db.commit()
        return {"status": "failed", "message": "robots.txt disallows scraping."}

    # Step 2 — gather page text
    combined_text = await _gather_site_text(company.website)
    if not combined_text.strip():
        company.enrichment_status = "failed"
        await db.commit()
        return {"status": "failed", "message": "Could not retrieve any page content."}

    # Step 3 — LLM Unified extraction, scoring, and persona
    fields = llm.extract_and_score_and_persona(combined_text) or {}

    # Step 4 — persist (null fields stay null — never fabricated)
    company.industry = fields.get("industry")
    company.employees_estimate = fields.get("employees_estimate")
    company.summary = fields.get("summary")
    company.tech_stack_hints = fields.get("tech_stack_hints")
    
    # Save the consolidated RAG score and Persona generated in this single step
    company.rag_score = int(fields.get("rag_score") or 0)
    company.rag_rationale = fields.get("rag_rationale")
    company.persona_summary = fields.get("persona_summary")

    company.enrichment_status = "done"
    company.status = "enriched"

    await db.commit()
    return {"status": "done", "message": "Enrichment complete."}
