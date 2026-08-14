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
    button_html = f'<a href="{meeting_link}" style="display: inline-block; padding: 10px 20px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 15px; margin-bottom: 15px;">Schedule a 10-Min Chat</a>'

    prompt = f"""You are a professional B2B sales writer. Write a short, genuine-sounding outreach email based on the AIDA template provided below.

Rules:
- You must strictly use the exact text structure provided in the "AIDA Template" below.
- Fill in the bracketed variables (like {{product/service}}, {{solve a problem}}, {{x%}}, {{A% to B%}}, etc.) with specific, realistic details based on the Persona Summary.
- Keep the tone professional.
- DO NOT wrap your output in markdown ```html code blocks. Just output the raw HTML tags.
- DO NOT include a "Subject:" line in the output.
- Structure your email using proper HTML <p> tags for paragraphs. Ensure there are blank lines between paragraphs.
- For the CTA button, replace "Do you have time to connect this week?" with EXACTLY this HTML code:
  {button_html}
- In the signature footer, include the sender name, company, and this website link: {website}

AIDA Template to follow:
Hi {contact_name or 'there'},

What if a {{product/service}} could help you {{solve a problem}}?

In the space of a year, we helped {{similar company name or 'our clients'}} achieve a {{x%}} increase in sales after implementing {sender_company}.

In addition to an increase in sales, {sender_company} helped them improve their overall workflow, increase efficiency, reduce response rate time, and improve customer satisfaction from {{A%}} to {{B%}}.

I’d love to talk to you about how {sender_company} could help your company increase sales and improve workflow. Do you have time to connect this week?

Persona summary for context:
{persona_summary}

Company: {company_name}
Sender: {sender_name}, {sender_company}"""

    html = _call_gemini(prompt)
    if html:
        html = html.replace("```html", "").replace("```", "").strip()
        return {"html": html, "draft_source": "gemini"}

    # Degraded-mode fallback: pipeline must never fully block on an API failure.
    fallback_html = (
        f"<p>Hi {contact_name or 'there'},</p>\n\n"
        f"<p>What if a specialized B2B solution could help {company_name or 'your company'} streamline operations and scale revenue?</p>\n\n"
        f"<p>In the space of a year, we helped our clients achieve a 35% increase in sales after implementing {sender_company}.</p>\n\n"
        f"<p>In addition to an increase in sales, {sender_company} helped them improve their overall workflow, increase efficiency, reduce response rate time, and improve customer satisfaction significantly.</p>\n\n"
        f"<p>I’d love to talk to you about how {sender_company} could help {company_name or 'your company'} increase sales and improve workflow.</p>\n\n"
        f"{button_html}\n\n"
        f"<p>— {sender_name}, {sender_company} &middot; {website}</p>"
    )
    return {"html": fallback_html, "draft_source": "template_fallback"}
