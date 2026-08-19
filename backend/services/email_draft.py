"""
services/email_draft.py — Module 6: Email Draft Generation (Template-Based NLP)

Generates a professional, personalised HTML email by merging enriched company
data into a set of hand-crafted sentence blocks.  No external API is used —
every field is selected deterministically based on what enrichment returned.

Pipeline:
  1. Load company + contact from DB.
  2. Build email content blocks from all available enrichment fields.
  3. Choose the best subject line variant based on available signals.
  4. Render the HTML body by assembling paragraph blocks.
  5. Persist as a Campaign with status = 'pending_review'.
"""
import logging
import re
import textwrap
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Campaign, Company, Contact
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── NLP helpers ───────────────────────────────────────────────────────────────

def _article(industry: str | None) -> str:
    """Return 'a' or 'an' appropriate for the industry label."""
    if not industry:
        return "a"
    first_letter = industry.strip().lower()[0]
    return "an" if first_letter in "aeiou" else "a"


def _industry_label(industry: str | None) -> str:
    """Convert snake_case industry to a readable noun phrase."""
    if not industry:
        return "your industry"
    return industry.replace("_", " ")


def _title(text: str) -> str:
    """Title-case a string, lower-casing minor words."""
    minor = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "for", "of", "with"}
    words = text.split()
    result = []
    for i, w in enumerate(words):
        result.append(w if (i > 0 and w.lower() in minor) else w.capitalize())
    return " ".join(result)


# ── Industry-aware pain points ────────────────────────────────────────────────

_PAIN_POINTS: dict[str, str] = {
    "restaurant": (
        "Restaurants often struggle to keep reservation information, menu updates, and "
        "supplier contacts accessible to staff without constant back-and-forth."
    ),
    "legal": (
        "Legal teams spend significant time hunting for precedents, case notes, and "
        "client documents scattered across different systems."
    ),
    "medical": (
        "Healthcare practices frequently deal with staff repeating the same procedural "
        "questions — an avoidable drain that adds up quickly across shifts."
    ),
    "hospitality": (
        "Hospitality businesses often see time lost when front-desk teams cannot "
        "instantly surface policies, room details, or event information for guests."
    ),
    "home_services": (
        "Home-services teams in the field often cannot quickly access job history, "
        "product specifications, or compliance checklists without calling back to the office."
    ),
}

_DEFAULT_PAIN_POINT = (
    "Teams typically lose hours each week searching for information buried across "
    "documents, inboxes, and spreadsheets — slowing down decisions and response times."
)


def _get_pain_point(industry: str | None) -> str:
    if not industry:
        return _DEFAULT_PAIN_POINT
    return _PAIN_POINTS.get(industry.lower(), _DEFAULT_PAIN_POINT)


# ── Industry-aware value propositions ─────────────────────────────────────────

_VALUE_PROPS: dict[str, str] = {
    "restaurant": (
        "We build lightweight knowledge tools that give your team instant, "
        "searchable access to everything from menu changes to supplier contacts — "
        "right from their phone, no extensive training required."
    ),
    "legal": (
        "We build AI-powered document search tools that let your team surface "
        "the right case note, clause, or precedent in seconds — without switching "
        "between multiple systems."
    ),
    "medical": (
        "We build searchable knowledge systems for healthcare teams so that "
        "protocols, FAQs, and patient-flow guidelines are always one quick search away."
    ),
    "hospitality": (
        "We build internal knowledge tools that let your front-desk and operations "
        "teams find policies, event details, and room information instantly — "
        "so guests never have to wait for an answer."
    ),
    "home_services": (
        "We build mobile-friendly knowledge tools that give field technicians "
        "instant access to job history, product specifications, and checklists — "
        "eliminating unnecessary calls back to the office."
    ),
}

_DEFAULT_VALUE_PROP = (
    "We build AI-powered search tools that give your team instant answers from "
    "your own content — documents, tickets, FAQs — so no one is stuck waiting "
    "or searching in the wrong place."
)


def _get_value_prop(industry: str | None) -> str:
    if not industry:
        return _DEFAULT_VALUE_PROP
    return _VALUE_PROPS.get(industry.lower(), _DEFAULT_VALUE_PROP)


# ── Content builders ──────────────────────────────────────────────────────────

def _extract_first_sentence(text: str) -> str:
    """Return the first meaningful sentence from a block of text."""
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for s in sentences:
        s = s.strip()
        if len(s) > 20:
            return s
    return sentences[0].strip() if sentences else ""


def _build_opener(company_name: str, industry: str | None, summary: str | None) -> str:
    """
    Build the email opener paragraph.
    Priority: use the company summary if available, otherwise fall back to industry.
    """
    industry_label = _industry_label(industry)
    art = _article(industry)

    if summary:
        first = _extract_first_sentence(summary)
        if first and len(first) > 20:
            first = textwrap.shorten(first, width=120, placeholder="…")
            return (
                f"I came across <strong>{company_name}</strong> recently — "
                f"{first[0].lower() + first[1:].rstrip('.')}. "
                f"Wanted to reach out with something that may be directly relevant "
                f"for {art} {industry_label} business like yours."
            )

    return (
        f"I came across <strong>{company_name}</strong> while researching "
        f"{industry_label} businesses in your area and wanted to reach out directly."
    )


def _build_tech_note(tech_stack: str | None) -> str | None:
    """If specific tech was detected on their site, add a personalised line."""
    if not tech_stack:
        return None
    tools = [t.strip().title() for t in tech_stack.split(",") if t.strip()]
    if not tools:
        return None
    if len(tools) == 1:
        tools_str = tools[0]
    elif len(tools) == 2:
        tools_str = f"{tools[0]} and {tools[1]}"
    else:
        tools_str = f"{', '.join(tools[:-1])}, and {tools[-1]}"
    return (
        f"I also noticed you are already using tools like <strong>{tools_str}</strong>. "
        f"Our solution integrates alongside your existing stack, so there is no "
        f"disruptive migration involved."
    )


def _build_subject(company_name: str, industry: str | None, rag_score: int | None) -> str:
    """Choose the best subject line variant based on available signals."""
    industry_label = _industry_label(industry)
    if rag_score and rag_score >= 70:
        return f"A quick idea for {company_name}"
    if industry and industry in _PAIN_POINTS:
        return f"Saving time for {_title(industry_label)} teams — {company_name}"
    return f"Something that might be useful for {company_name}"


# ── HTML email renderer ───────────────────────────────────────────────────────

_EMAIL_CSS = """\
    body {
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 15px;
      line-height: 1.75;
      color: #1a202c;
      background-color: #f7f8fc;
      margin: 0;
      padding: 0;
    }
    .wrapper {
      max-width: 600px;
      margin: 32px auto;
      padding: 40px 40px 32px;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }
    p { margin: 0 0 18px; }
    strong { color: #1a202c; }
    .divider {
      border: none;
      border-top: 1px solid #e2e8f0;
      margin: 28px 0;
    }
    .cta-btn {
      display: inline-block;
      padding: 12px 28px;
      background-color: #1d4ed8;
      color: #ffffff !important;
      text-decoration: none;
      border-radius: 6px;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.3px;
      margin: 4px 0 24px;
    }
    .signature {
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      color: #374151;
      line-height: 1.6;
    }
    .signature a { color: #1d4ed8; text-decoration: none; }
    .footer-note {
      font-family: Arial, Helvetica, sans-serif;
      font-size: 12px;
      color: #9ca3af;
      margin-top: 28px;
    }"""


def _render_html(
    contact_name: str,
    company_name: str,
    opener: str,
    pain_point: str,
    value_prop: str,
    tech_note: str | None,
    meeting_link: str,
    sender_name: str,
    sender_company: str,
    website: str,
) -> str:
    """Assemble the final HTML email from paragraph blocks."""
    tech_para = f"\n    <p>{tech_note}</p>" if tech_note else ""
    cta_html = (
        f'<a href="{meeting_link}" class="cta-btn">Schedule a 15-Minute Call</a>'
        if meeting_link
        else ""
    )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
{_EMAIL_CSS}
</style>
</head>
<body>
<div class="wrapper">

  <p>Hi {contact_name},</p>

  <p>{opener}</p>

  <p>{pain_point}</p>

  <p>{value_prop}</p>{tech_para}

  <p>
    If any of this resonates, I would be happy to show you a brief, no-obligation
    walkthrough tailored to <strong>{company_name}</strong>. Even a 15-minute
    conversation would be enough to determine whether there is a genuine fit.
  </p>

  {cta_html}

  <hr class="divider">

  <div class="signature">
    <strong>{sender_name}</strong><br>
    {sender_company}<br>
    <a href="{website}">{website}</a>
  </div>

  <p class="footer-note">
    You are receiving this message because your business appeared in a relevant
    industry search. If this is not of interest, simply reply with
    &ldquo;Not interested&rdquo; and we will ensure you are not contacted again.
  </p>

</div>
</body>
</html>"""


# ── Public entry point ────────────────────────────────────────────────────────

async def generate_draft(company_id: str, db: AsyncSession) -> dict:
    """
    Generate a professionally personalised HTML email draft for a company
    using traditional NLP template merging — no LLM or external API required.

    Personalisation is driven entirely by enrichment data:
      - industry        → selects pain-point and value-proposition paragraph variants
      - summary         → extracts the first meaningful sentence as the opener hook
      - tech_stack_hints → adds an optional tool-mention paragraph
      - rag_score       → influences subject line selection

    Saves the result as a Campaign with status = 'pending_review'.
    Returns { "status": "done"|"failed", "campaign_id": str, "subject": str }.
    """
    # ── Load company ──────────────────────────────────────────────────────────
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        return {"status": "failed", "message": "Company not found."}

    # ── Load primary contact ──────────────────────────────────────────────────
    contact_result = await db.execute(
        select(Contact)
        .where(Contact.company_id == company_id)
        .limit(1)
    )
    contact = contact_result.scalar_one_or_none()
    contact_name = (contact.name if (contact and contact.name) else "there")

    # ── Gather enrichment signals ─────────────────────────────────────────────
    industry     = company.industry          # e.g. "restaurant", "legal", None
    summary      = company.summary           # meta-description / first two sentences
    tech_stack   = company.tech_stack_hints  # e.g. "wordpress, shopify"
    rag_score    = company.rag_score
    company_name = company.name or "your business"

    meeting_link   = settings.CALENDAR_LINK
    sender_name    = settings.SENDER_NAME
    sender_company = settings.SENDER_COMPANY
    website        = "https://www.vantrade.online/"

    # ── Build content blocks ──────────────────────────────────────────────────
    opener     = _build_opener(company_name, industry, summary)
    pain_point = _get_pain_point(industry)
    value_prop = _get_value_prop(industry)
    tech_note  = _build_tech_note(tech_stack)
    subject    = _build_subject(company_name, industry, rag_score)

    # ── Render HTML ───────────────────────────────────────────────────────────
    draft_html = _render_html(
        contact_name=contact_name,
        company_name=company_name,
        opener=opener,
        pain_point=pain_point,
        value_prop=value_prop,
        tech_note=tech_note,
        meeting_link=meeting_link,
        sender_name=sender_name,
        sender_company=sender_company,
        website=website,
    )

    # ── Persist campaign record ───────────────────────────────────────────────
    campaign = Campaign(
        company_id=company.id,
        contact_id=contact.id if contact else None,
        subject=subject,
        draft_html=draft_html,
        draft_source="template_nlp",
        status="pending_review",
    )
    db.add(campaign)
    company.status = "drafted"

    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Draft generated (template_nlp) for %s — subject: %s",
        company_name,
        subject,
    )
    return {
        "status": "done",
        "campaign_id": str(campaign.id),
        "subject": subject,
    }
