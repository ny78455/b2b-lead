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

# Generic boilerplate openers from persona.build_persona_text() that make weak
# hooks on their own — skip these in favor of a more concrete sentence.
_WEAK_HOOK_PATTERNS = (
    re.compile(r"^\S.*\boperates in the\b.*\bindustry\.?$", re.IGNORECASE),
    re.compile(r"^Estimated size:", re.IGNORECASE),
    re.compile(r"^Purchase-intent score:", re.IGNORECASE),
)


def _pick_personalization_detail(text: str) -> str:
    """
    Pick the most concrete, specific-sounding sentence out of persona_summary
    to use as the fallback email's hook. Prefers sentences with real detected
    signals (e.g. "Matched signals: ...") or tech-stack mentions over generic
    template boilerplate like "X operates in the Y industry."
    """
    if not text:
        return ""

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return ""

    # 1. Prefer a sentence naming concrete RAG-fit signals — most specific.
    for s in sentences:
        if "matched signals" in s.lower() or "signals:" in s.lower():
            return s

    # 2. Next best: a sentence mentioning specific tools/tech found on their site.
    for s in sentences:
        if "tech" in s.lower() or "tools mentioned" in s.lower():
            return s

    # 3. Otherwise, first sentence that isn't generic boilerplate.
    for s in sentences:
        if not any(p.search(s) for p in _WEAK_HOOK_PATTERNS):
            return s

    # 4. Nothing better available — fall back to the first sentence anyway.
    return sentences[0]


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
    # real, specific detail is available from persona_summary rather than
    # staying fully generic — but it is still clearly marked as
    # template_fallback so it's never mistaken for a personalized draft
    # downstream. Kept short and conversational (reply-optimized), since a
    # degraded-mode email has no LLM-crafted nuance to lean on otherwise:
    # one concrete hook, one plain-English pain point, one low-friction
    # question as the primary ask, the meeting link only as a secondary
    # option, and a PS line (reliably read even when the body is skimmed).
    hook = _pick_personalization_detail(persona_summary)
    hook = hook.rstrip(".") if hook else ""
    company_label = company_name or "your team"

    if hook:
        opener = f"Came across {company_name or 'your company'} — {hook[0].lower() + hook[1:]}."
    else:
        opener = f"Came across {company_label} and wanted to reach out directly."

    fallback_html = (
        f"<p>Hi {contact_name or 'there'},</p>\n\n"
        f"<p>{opener}</p>\n\n"
        f"<p>Most teams in that spot end up losing hours to the same repeated "
        f"questions buried across docs, tickets, and inboxes. We build "
        f"AI search tools that let your team (or customers) get a straight "
        f"answer instantly from your own content, instead of digging for it.</p>\n\n"
        f"<p>Is that something worth a quick reply about — even just to say "
        f"whether it's relevant right now?</p>\n\n"
        f"<p>Or if it's easier to just grab time:</p>\n\n"
        f"{button_html}\n\n"
        f"<p>— {sender_name}, {sender_company} &middot; {website}</p>\n\n"
        f"<p style=\"font-size: 13px; color: #666;\">P.S. Even a one-line "
        f"\"not right now\" is genuinely useful — I'll make sure we don't "
        f"bother {company_label} again.</p>"
    )
    return {"html": fallback_html, "draft_source": "template_fallback"}