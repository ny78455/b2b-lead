"""
services/llm.py — LLM client: Gemini API

Only exactly one LLM call per lead is permitted: email drafting.
Everything else is rule-based.
"""
import logging
import re
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_gemini_model = None

def _get_gemini_model():
    """Lazy-init the Gemini API client."""
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(model_name=settings.GEMINI_MODEL)
        logger.info("Gemini API client initialised (model: %s).", settings.GEMINI_MODEL)
        return _gemini_model
    except Exception as exc:
        logger.error("Failed to initialise Gemini API client: %s", exc)
        return None

def _call_gemini(prompt: str) -> str | None:
    """Call the Gemini API. Returns text or None."""
    model = _get_gemini_model()
    if model is None:
        return None
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        return None


# ── 1. Query generation (Module 1) ────────────────────────────────────────────

QUERY_TEMPLATES = [
    "{niche} in {location}",
    "best {niche} near {location}",
    "top rated {niche} {location}",
    "{niche} services {location}",
    "24 hour {niche} {location}",
    "{niche} near {location}",
]

def generate_queries(seed_niches: list[str], seed_locations: list[str], n: int = 6) -> list[str]:
    """
    Expand seed niches × locations deterministically into Maps search queries.
    """
    queries = []
    for niche in seed_niches:
        for location in seed_locations:
            for template in QUERY_TEMPLATES[:n]:
                queries.append(template.format(niche=niche, location=location))
    return list(dict.fromkeys(queries))  # de-dupe, preserve order


# ── 6. Email draft (Module 6) ─────────────────────────────────────────────────

def _first_sentence(text: str) -> str:
    """Grab the first real sentence out of persona_summary for the fallback path."""
    if not text:
        return ""
    match = re.split(r"(?<=[.!?])\s+", text.strip())
    return match[0].strip() if match else text.strip()


def draft_email(
    persona_summary: str,
    company_name: str,
    contact_name: str,
    sender_name: str,
    sender_company: str,
    meeting_link: str,
    website: str,
) -> dict:
    """
    Draft a personalized email using Gemini API, with a deterministic fallback
    if the API call fails. The model is given the company's actual persona
    data and freedom to write its own structure/angle — it is NOT locked into
    reproducing the same sentence-for-sentence template on every lead.

    Returns {"html": str, "draft_source": "gemini" | "template_fallback"}
    """
    button_html = (
        f'<a href="{meeting_link}" style="display: inline-block; padding: 10px 20px; '
        f'background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; '
        f'font-weight: bold; margin-top: 15px; margin-bottom: 15px;">Schedule a 10-Min Chat</a>'
    )

    prompt = f"""You are a professional B2B sales writer. Write a short, genuine-sounding
outreach email (120-160 words) for the specific company below.

Persona summary (the ONLY facts you may reference about this company):
{persona_summary}

Company: {company_name}
Contact name: {contact_name or 'there'}
Sender: {sender_name}, {sender_company}

Rules:
- Write original wording for THIS company — do not reuse boilerplate phrasing
  you'd give any other lead. Two different companies with different personas
  should read as genuinely different emails, not the same email with nouns
  swapped.
- Use ONLY facts present in the persona summary above. Never invent news,
  statistics, client names, or percentage results that aren't given to you.
  If the persona summary doesn't mention a stat, don't make one up — describe
  the value proposition in plain terms instead.
- Open by referencing one specific, real detail about {company_name} from the
  persona summary (their industry, a signal you were given, whatever is most
  concrete) — not a generic greeting.
- Identify ONE plausible pain point for a company like this and explain, in
  your own words, how a RAG-based knowledge/support solution addresses it.
- No superlatives, no fake urgency, no "I noticed you're the perfect fit"
  filler, no invented case studies.
- End with a single, low-friction question inviting a reply or a quick chat.
- Output CLEAN, VALID HTML only — no markdown code fences, no "Subject:" line.
- Use <p> tags for paragraphs with blank lines between them.
- Include this exact CTA button HTML once, placed naturally near the end,
  in place of any closing question about scheduling:
  {button_html}
- In the signature footer, include the sender name, company, and this exact
  website link: {website}"""

    html = _call_gemini(prompt)
    if html:
        html = html.replace("```html", "").replace("```", "").strip()
        return {"html": html, "draft_source": "gemini"}

    # Degraded-mode fallback: pipeline must never fully block on an API failure.
    # This is a plain template merge, NOT an LLM call, so it leans on whatever
    # real detail is available from persona_summary rather than staying fully
    # generic — but it is still clearly marked as template_fallback so it's
    # never mistaken for a personalized draft downstream.
    hook = _first_sentence(persona_summary) or f"{company_name or 'your company'} looks like a strong fit for what we do."

    fallback_html = (
        f"<p>Hi {contact_name or 'there'},</p>\n\n"
        f"<p>{hook}</p>\n\n"
        f"<p>That's usually the point where teams start losing time to repetitive "
        f"questions and scattered documentation — which is exactly what a "
        f"RAG-based knowledge assistant from {sender_company} is built to fix.</p>\n\n"
        f"<p>Worth a quick look for {company_name or 'your team'}? I'd love to hear "
        f"what's currently working and where it's falling short.</p>\n\n"
        f"{button_html}\n\n"
        f"<p>— {sender_name}, {sender_company} &middot; {website}</p>"
    )
    return {"html": fallback_html, "draft_source": "template_fallback"}