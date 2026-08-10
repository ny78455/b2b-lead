"""
services/sender.py — Module 8: Email Sending (SendGrid)

Compliance rules enforced on every send:
  1. Check suppression list — abort if suppressed.
  2. Enforce 2,000/day hard cap (re-counted from DB on every call).
  3. Token-bucket rate limit: max HOURLY_SEND_LIMIT per hour.
  4. Replace {{unsubscribe_link}} token with a real signed URL.
  5. Log sent_at on success.

No email is ever sent without explicit human approval (status = 'approved').
This service is only called AFTER a human clicks "Approve & Send" in the UI.
"""
import hashlib
import hmac
import logging
import time
from datetime import datetime, date, timezone

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, From, HtmlContent, Subject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.models import Campaign, Company, Contact
from backend.services.suppression import is_suppressed, SuppressionError
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── In-memory token bucket (per process) ─────────────────────────────────────
_bucket_tokens: float = float(settings.HOURLY_SEND_LIMIT)
_bucket_last_refill: float = time.monotonic()
_REFILL_RATE: float = settings.HOURLY_SEND_LIMIT / 3600.0  # tokens per second


def _consume_rate_limit_token() -> bool:
    """Return False if the hourly rate limit is exhausted."""
    global _bucket_tokens, _bucket_last_refill
    now = time.monotonic()
    elapsed = now - _bucket_last_refill
    _bucket_tokens = min(
        settings.HOURLY_SEND_LIMIT,
        _bucket_tokens + elapsed * _REFILL_RATE,
    )
    _bucket_last_refill = now
    if _bucket_tokens >= 1:
        _bucket_tokens -= 1
        return True
    return False


# ── Daily cap ─────────────────────────────────────────────────────────────────

async def _count_sent_today(db: AsyncSession) -> int:
    """Re-count rows sent today from DB — not an in-memory counter."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count()).select_from(Campaign).where(
            Campaign.status == "sent",
            Campaign.sent_at >= today_start,
        )
    )
    return result.scalar() or 0


# ── Unsubscribe link generation ───────────────────────────────────────────────

def _make_unsubscribe_url(campaign_id: str) -> str:
    """
    Generate a signed unsubscribe URL.
    The token is an HMAC of the campaign_id using the SendGrid API key as secret.
    """
    secret = settings.SENDGRID_API_KEY.encode()
    token = hmac.new(secret, campaign_id.encode(), hashlib.sha256).hexdigest()
    return f"{settings.UNSUBSCRIBE_BASE_URL}/api/unsubscribe?campaign_id={campaign_id}&token={token}"


def verify_unsubscribe_token(campaign_id: str, token: str) -> bool:
    """Verify the HMAC token from an unsubscribe link click."""
    expected = hmac.new(
        settings.SENDGRID_API_KEY.encode(),
        campaign_id.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, token)


# ── Main send function ────────────────────────────────────────────────────────

async def send_campaign(campaign_id: str, db: AsyncSession) -> dict:
    """
    Send an approved campaign email via SendGrid.
    Called ONLY after human approval — never autonomously.
    """
    # Load campaign
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        return {"status": "failed", "message": "Campaign not found."}

    if campaign.status != "approved":
        return {"status": "failed", "message": f"Campaign status is '{campaign.status}', not 'approved'."}

    # Load contact email
    if not campaign.contact_id:
        return {"status": "failed", "message": "No contact linked to this campaign."}

    contact_result = await db.execute(select(Contact).where(Contact.id == campaign.contact_id))
    contact = contact_result.scalar_one_or_none()
    if not contact:
        return {"status": "failed", "message": "Contact not found."}

    recipient_email = contact.email

    # ── Compliance gate 1: suppression list ───────────────────────────────────
    if await is_suppressed(recipient_email, db):
        campaign.status = "rejected"
        await db.commit()
        return {"status": "failed", "message": f"{recipient_email} is on the suppression list."}

    # ── Compliance gate 2: daily cap (re-counted from DB) ─────────────────────
    sent_today = await _count_sent_today(db)
    if sent_today >= settings.DAILY_SEND_LIMIT:
        return {
            "status": "failed",
            "message": f"Daily send cap ({settings.DAILY_SEND_LIMIT}) reached ({sent_today} sent today).",
        }

    # ── Compliance gate 3: hourly rate limit ──────────────────────────────────
    if not _consume_rate_limit_token():
        return {"status": "failed", "message": "Hourly rate limit reached. Try again shortly."}

    # ── Replace unsubscribe token ──────────────────────────────────────────────
    unsubscribe_url = _make_unsubscribe_url(str(campaign.id))
    html_body = (campaign.draft_html or "").replace("{{unsubscribe_link}}", unsubscribe_url)

    # Final compliance check: ensure unsubscribe link is present
    if unsubscribe_url not in html_body:
        html_body += (
            f'\n<p style="font-size:11px;color:#888;text-align:center;">'
            f'<a href="{unsubscribe_url}">Unsubscribe</a></p>'
        )

    # ── Send via SendGrid ──────────────────────────────────────────────────────
    try:
        sg = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=From(settings.SENDER_EMAIL, settings.SENDER_NAME),
            to_emails=To(recipient_email),
            subject=Subject(campaign.subject or "Hello from our team"),
            html_content=HtmlContent(html_body),
        )
        response = sg.send(message)
        message_id = response.headers.get("X-Message-Id", "")

        campaign.status = "sent"
        campaign.sent_at = datetime.now(timezone.utc)
        campaign.sendgrid_message_id = message_id

        # Load company and update status
        company_result = await db.execute(select(Company).where(Company.id == campaign.company_id))
        company = company_result.scalar_one_or_none()
        if company:
            company.status = "sent"

        await db.commit()
        logger.info("Campaign %s sent to %s (SG msg: %s)", campaign_id, recipient_email, message_id)
        return {"status": "sent", "message_id": message_id}

    except Exception as exc:
        logger.error("SendGrid error for campaign %s: %s", campaign_id, exc)
        return {"status": "failed", "message": str(exc)}
