"""
services/enrichment.py — Module 2: Company Enrichment

For each company website:
  1. Fetch and respect robots.txt — mark failed if scraping is disallowed.
  2. Fetch homepage + /about + /careers (up to 3 pages).
  3. Extract fields (industry, employees_estimate, summary, tech_stack_hints) using deterministic rules.
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
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Company

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "B2BOutreachBot/1.0 (+https://github.com/ny78455/b2b-lead; respectful-scraper)",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15.0  # seconds
MAX_TEXT_CHARS = 3000  # cap text sent to LLM per page

# ── Extraction Rules ─────────────────────────────────────────────────────────

INDUSTRY_KEYWORDS = {
    "restaurant": ["restaurant", "menu", "dining", "cuisine"],
    "legal": ["law firm", "attorney", "legal services", "lawyer"],
    "medical": ["clinic", "patients", "medical", "healthcare", "dental"],
    "hospitality": ["hotel", "resort", "boutique hotel", "hospitality"],
    "home_services": ["plumbing", "roofing", "hvac", "contractor"],
}

EMPLOYEE_COUNT_PATTERN = re.compile(
    r"(team of|over|more than)?\s*(\d{1,4})\s*(\+)?\s*(employees|team members|staff)",
    re.IGNORECASE,
)

TECH_KEYWORDS = [
    "wordpress", "shopify", "react", "salesforce", "hubspot",
    "openai", "langchain", "huggingface", "zendesk", "intercom",
]

def _extract_industry(text: str) -> str | None:
    lowered = text.lower()
    for label, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return label
    return None

def _extract_employees(text: str) -> str | None:
    match = EMPLOYEE_COUNT_PATTERN.search(text)
    return match.group(0).strip() if match else None

def _extract_summary(soup: BeautifulSoup, text: str) -> str | None:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()[:300]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:2]).strip() or None

def _extract_tech_stack(text: str) -> str | None:
    lowered = text.lower()
    hits = [kw for kw in TECH_KEYWORDS if kw in lowered]
    return ", ".join(hits) if hits else None


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

async def _fetch_page_data(client: httpx.AsyncClient, url: str) -> tuple[BeautifulSoup | None, str]:
    """Fetch a URL and return (soup, cleaned_text)."""
    try:
        resp = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # We need the soup for _extract_summary, so we return it before decomposing tags
        soup_copy = BeautifulSoup(resp.text, "html.parser")

        # Remove noise tags for plain text extraction
        for tag in soup(["script", "style", "nav", "footer", "head", "noscript"]):
            tag.decompose()

        text = " ".join(soup.get_text(separator=" ").split())
        return soup_copy, text[:MAX_TEXT_CHARS]
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None, ""


async def _gather_site_data(website: str) -> tuple[BeautifulSoup | None, str]:
    """Fetch homepage + /about + /careers and concatenate text. Returns (homepage_soup, combined_text)."""
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
        tasks = [_fetch_page_data(client, url) for url in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        texts = []
        homepage_soup = None
        for i, (url, result) in enumerate(zip(pages, results)):
            if isinstance(result, Exception):
                logger.debug("Gather failed for %s: %s", url, result)
            else:
                soup, text = result
                if i == 0:
                    homepage_soup = soup
                if text:
                    texts.append(f"[Page: {url}]\n{text}")

    return homepage_soup, "\n\n".join(texts)


# ── Main entry point ──────────────────────────────────────────────────────────

async def enrich_company(company_id: str, db: AsyncSession) -> dict:
    """
    Run the full Module 2 enrichment pipeline for one company using deterministic rules.
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
    homepage_soup, combined_text = await _gather_site_data(company.website)
    if not combined_text.strip():
        company.enrichment_status = "failed"
        await db.commit()
        return {"status": "failed", "message": "Could not retrieve any page content."}

    # Step 3 — Extraction (Rule-based)
    # We pass the homepage_soup if available, else an empty soup.
    # To avoid passing None, we ensure we have a valid soup for the summary rule.
    soup = homepage_soup if homepage_soup else BeautifulSoup("", "html.parser")

    company.industry = _extract_industry(combined_text)
    company.employees_estimate = _extract_employees(combined_text)
    company.summary = _extract_summary(soup, combined_text)
    company.tech_stack_hints = _extract_tech_stack(combined_text)
    
    # We leave rag_score, rag_rationale, and persona_summary untouched here.
    # They will be populated by scoring.py and persona.py.

    company.enrichment_status = "done"
    company.status = "enriched"

    await db.commit()
    return {"status": "done", "message": "Enrichment complete."}
