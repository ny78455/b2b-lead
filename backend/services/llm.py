"""
services/llm.py — LLM client: Gemini API

Only exactly one LLM call per lead is permitted: email drafting.
Everything else is rule-based.
"""
import logging
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
    Draft an email using Gemini API, with a fallback to a deterministic template.
    Returns {"html": str, "draft_source": "gemini" | "template_fallback"}
    """
    prompt = f"""You are a professional B2B sales writer. Write a short, genuine-sounding
outreach email (120-160 words).

Rules:
- Use ONLY facts present in the persona summary below. Never invent news, numbers,
  or claims about the recipient's company.
- Reference exactly one specific, verifiable detail about them.
- Name exactly one plausible pain point and how a RAG solution helps.
- End with a call to action to schedule a 10-minute chat using this meeting link: {meeting_link}
- Output CLEAN and VALID HTML only. DO NOT wrap your output in markdown ```html code blocks. Just output the raw HTML tags.
- DO NOT include a "Subject:" line in the output.
- Structure your email using proper HTML <p> tags for paragraphs. Use `<br>` sparingly. Ensure there are blank lines between paragraphs.
- For the call to action, use EXACTLY this HTML code for the button:
  <a href="{meeting_link}" style="display: inline-block; padding: 10px 20px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 15px; margin-bottom: 15px;">Schedule a 10-Min Chat</a>
- In the signature footer, include the sender name, company, and this website link: {website}
- No superlatives, no fake urgency, no "I noticed you're the perfect fit" filler.

Persona summary:
{persona_summary}

Company: {company_name}
Contact name: {contact_name}
Sender: {sender_name}, {sender_company}"""

    html = _call_gemini(prompt)
    if html:
        html = html.replace("```html", "").replace("```", "").strip()
        return {"html": html, "draft_source": "gemini"}

    # Degraded-mode fallback: pipeline must never fully block on an API failure.
    # This is a plain template merge, NOT an LLM call — mark it clearly so
    # these drafts are never mistaken for personalized output downstream.
    
    button_html = f'<a href="{meeting_link}" style="display: inline-block; padding: 10px 20px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 15px; margin-bottom: 15px;">Schedule a 10-Min Chat</a>'
    
    fallback_html = (
        f"<p>Hi {contact_name or 'there'},</p>\n\n"
        f"<p>{persona_summary}</p>\n\n"
        f"{button_html}\n\n"
        f"<p>— {sender_name}, {sender_company} &middot; {website}</p>"
    )
    return {"html": fallback_html, "draft_source": "template_fallback"}
