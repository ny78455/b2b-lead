"""
services/llm.py — Single Gemma client wrapping google-generativeai.

All 5 LLM use-cases in the MVP flow through this module:
  1. generate_queries()   — Module 1: expand seed niches to Maps search queries
  2. score_rag()          — Module 3: 0-100 RAG-fit score + rationale
  3. summarize_persona()  — Module 5: 3-5 sentence company summary
  4. draft_email()        — Module 6: HTML outreach email
  5. classify_reply()     — Module 9: classify inbound reply into 4 buckets

Design constraints (from spec §2):
  - Never invent facts not present in the evidence passed in.
  - Return JSON for structured calls; retry once on parse failure.
  - A bad model response must never block the pipeline — callers get None / fallback.
"""
import json
import logging
import re
from typing import Optional

import google.generativeai as genai
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure API key once at module import
genai.configure(api_key=settings.GEMINI_API_KEY)
_model = genai.GenerativeModel(model_name=settings.GEMMA_MODEL)


def _call(prompt: str) -> str:
    """Raw model call; raises on network/auth errors."""
    response = _model.generate_content(prompt)
    return response.text.strip()


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from model output, tolerating markdown fences."""
    # Strip ```json ... ``` fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _call_json(prompt: str) -> Optional[dict]:
    """Call model and parse JSON; retry once on parse failure."""
    for attempt in range(2):
        try:
            raw = _call(prompt)
            result = _parse_json(raw)
            if result is not None:
                return result
            logger.warning("JSON parse failed (attempt %d). Raw: %s", attempt + 1, raw[:200])
        except Exception as exc:
            logger.error("LLM call error (attempt %d): %s", attempt + 1, exc)
    return None


# ── 1. Query generation (Module 1) ────────────────────────────────────────────

def generate_queries(seed_niches: list[str], seed_locations: list[str], n: int = 5) -> list[str]:
    """
    Expand seed niches × locations into natural Google Maps search queries.
    Falls back to simple `niche + location` combinations on parse failure.
    """
    prompt = f"""You are helping build search queries for a local business lead-generation
tool that searches Google Maps.

Business niches: {', '.join(seed_niches)}
Target locations: {', '.join(seed_locations)}

For EACH niche, write {n} distinct, natural-sounding Google Maps search queries that
combine that niche with one or more of the target locations.
Vary the phrasing the way a real person types into Google Maps search.
Do not repeat the same query twice.

Return ONLY a JSON array of strings. No markdown, no commentary, no keys."""

    try:
        raw = _call(prompt)
        result = _parse_json(raw)
        if isinstance(result, list) and result:
            return [str(q) for q in result]
    except Exception as exc:
        logger.error("Query generation failed: %s", exc)

    # Fallback: simple cross-product
    fallback = [f"{niche} in {loc}" for niche in seed_niches for loc in seed_locations]
    logger.warning("Using fallback queries (%d total).", len(fallback))
    return fallback


# ── 2. RAG opportunity score (Module 3) ───────────────────────────────────────

def score_rag(enrichment_text: str) -> Optional[dict]:
    """
    Returns {"score": int (0-100), "rationale": str} or None on failure.
    Never invents facts — scores only on evidence provided.
    """
    prompt = f"""You are a B2B solutions analyst. Score how likely this company would
benefit from a Retrieval-Augmented Generation (RAG) system, based ONLY on the
evidence provided. Do not invent facts.

Checklist to consider:
- Do they show signs of a large knowledge base, documentation, or support volume?
- Do they mention AI/LLM/chatbot initiatives already?
- Does their industry typically carry compliance-heavy documents (legal, medical, financial)?

Evidence:
{enrichment_text}

Return JSON only:
{{"score": <integer 0-100>, "rationale": "<one sentence, evidence-based>"}}"""

    return _call_json(prompt)


# ── 3. Persona summary (Module 5) ─────────────────────────────────────────────

def summarize_persona(
    enrichment_text: str,
    rag_score: int,
    purchase_score: int,
) -> Optional[str]:
    """
    Returns a 3-5 sentence plain-text persona summary.
    If a fact is not confirmed, it is omitted — never speculated.
    """
    prompt = f"""Summarize this company in 3-5 sentences for a sales rep.
Use ONLY the evidence given. If a fact is not confirmed, omit it —
never speculate or fabricate specifics (funding amounts, headcount,
customer names, etc.).

Evidence:
{enrichment_text}
Scores: rag_score={rag_score}, purchase_score={purchase_score}

Output plain text only (no JSON, no markdown headers)."""

    try:
        return _call(prompt)
    except Exception as exc:
        logger.error("Persona summary failed: %s", exc)
        return None


# ── 4. Email draft (Module 6) ─────────────────────────────────────────────────

def draft_email(
    persona_summary: str,
    company_name: str,
    contact_name: str,
    sender_name: str,
    sender_company: str,
) -> Optional[str]:
    """
    Returns a valid HTML string (120-160 words) or None on failure.
    The {{unsubscribe_link}} token is preserved in the output for the sender
    service to replace with a real URL before sending.
    """
    prompt = f"""You are a professional B2B sales writer. Write a short, genuine-sounding
outreach email (120-160 words).

Rules:
- Use ONLY facts present in the persona summary below. Never invent news, numbers,
  or claims about the recipient's company.
- Reference exactly one specific, verifiable detail about them.
- Name exactly one plausible pain point and how a RAG solution helps.
- End with a single low-friction question inviting a reply.
- Output VALID HTML only: include a header, greeting, body paragraphs, one CTA
  <a> button, and a footer containing the sender name/company and the literal
  token {{{{unsubscribe_link}}}} as an anchor href — e.g.:
  <a href="{{{{unsubscribe_link}}}}">Unsubscribe</a>
- No superlatives, no fake urgency, no "I noticed you're the perfect fit" filler.

Persona summary:
{persona_summary}

Company: {company_name}
Contact name: {contact_name}
Sender: {sender_name}, {sender_company}"""

    try:
        html = _call(prompt)
        # Guarantee the unsubscribe token is present (compliance check)
        if "{{unsubscribe_link}}" not in html and "unsubscribe_link" not in html:
            html += (
                '\n<p style="font-size:11px;color:#888;">'
                '<a href="{{unsubscribe_link}}">Unsubscribe</a></p>'
            )
        return html
    except Exception as exc:
        logger.error("Email draft failed: %s", exc)
        return None


# ── 5. Reply classification (Module 9) ────────────────────────────────────────

def classify_reply(reply_text: str) -> Optional[dict]:
    """
    Returns {"classification": str, "sentiment": str} or None on failure.
    Classification buckets: interested | not_interested | needs_info | auto_reply_or_oof
    """
    prompt = f"""Classify this email reply into exactly one category:
interested | not_interested | needs_info | auto_reply_or_oof

Return JSON only:
{{"classification": "<category>", "sentiment": "positive|neutral|negative"}}

Reply text:
{reply_text[:4000]}"""   # cap at 4k chars to avoid token blowout

    return _call_json(prompt)
