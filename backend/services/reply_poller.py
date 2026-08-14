"""
services/reply_poller.py — Module 9: Reply Detection & Classification

Polls the configured IMAP inbox every IMAP_POLL_INTERVAL_SECONDS.
For each new reply:
  1. Match In-Reply-To / References headers to a campaign_id.
  2. Call Gemma LLM to classify: interested | not_interested | needs_info | auto_reply_or_oof
  3. Insert a row into the replies table.

Runs as a background asyncio task started at FastAPI startup.
"""
import asyncio
import email
import email.policy
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import aioimaplib
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.database import AsyncSessionLocal
from backend.models import Campaign, Reply
from sqlalchemy import select, update

logger = logging.getLogger(__name__)
settings = get_settings()

def classify_reply(body: str) -> dict:
    text = body.lower()

    if any(p in text for p in ["out of office", "automatic reply", "auto-reply", "vacation responder"]):
        return {"classification": "auto_reply_or_oof", "sentiment": "neutral"}
    if any(p in text for p in ["unsubscribe", "not interested", "remove me", "stop emailing", "no thank you"]):
        return {"classification": "not_interested", "sentiment": "negative"}
    if any(p in text for p in ["schedule", "book a call", "demo", "sounds good", "let's talk", "interested", "sign me up"]):
        return {"classification": "interested", "sentiment": "positive"}
    # Default: ambiguous replies route to a human rather than being guessed at.
    return {"classification": "needs_info", "sentiment": "neutral"}

# Track processed message IDs to avoid double-classification
_processed_imap_ids: set[str] = set()


# ── IMAP helpers ──────────────────────────────────────────────────────────────

async def _connect_imap() -> aioimaplib.IMAP4_SSL:
    """Open and authenticate an IMAP SSL connection."""
    client = aioimaplib.IMAP4_SSL(host=settings.IMAP_HOST, port=settings.IMAP_PORT)
    await client.wait_hello_from_server()
    await client.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
    await client.select(settings.IMAP_FOLDER)
    return client


async def _fetch_unseen_uids(client: aioimaplib.IMAP4_SSL) -> list[str]:
    """Return message sequence numbers of UNSEEN messages."""
    _, data = await client.search("UNSEEN")
    raw = data[0].decode() if data and data[0] else ""
    return [num for num in raw.split() if num]


async def _fetch_message(client: aioimaplib.IMAP4_SSL, num: str) -> Optional[email.message.Message]:
    """Fetch RFC822 message by sequence number and parse it."""
    try:
        _, data = await client.fetch(num, "(RFC822)")
        for part in data:
            if isinstance(part, tuple):
                return email.message_from_bytes(part[1], policy=email.policy.default)
    except Exception as exc:
        logger.error("Failed to fetch message %s: %s", num, exc)
    return None


def _extract_text(msg: email.message.Message) -> str:
    """Extract plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _find_campaign_id(msg: email.message.Message) -> Optional[str]:
    """
    Extract our campaign UUID from In-Reply-To or References headers.
    We embed the campaign_id in the Message-ID header when sending:
      Message-ID: <campaign-{uuid}@ourserver.com>
    """
    uuid_pattern = re.compile(
        r"campaign-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        re.I,
    )
    for header in ("In-Reply-To", "References", "Message-Id"):
        value = msg.get(header, "")
        m = uuid_pattern.search(value)
        if m:
            return m.group(1)
    return None


# ── Classification & persistence ──────────────────────────────────────────────

async def _process_message(msg: email.message.Message, db: AsyncSession) -> None:
    """Classify and store one reply message."""
    imap_message_id = msg.get("Message-Id", "")

    if imap_message_id in _processed_imap_ids:
        return
    _processed_imap_ids.add(imap_message_id)

    campaign_id = _find_campaign_id(msg)
    if not campaign_id:
        logger.debug("Could not match reply to a campaign: %s", imap_message_id)
        return

    # Verify campaign exists
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        logger.warning("Campaign %s not found for reply %s", campaign_id, imap_message_id)
        return

    # Extract text and classify
    body = _extract_text(msg)
    classification_result = classify_reply(body)
    classification = classification_result.get("classification")
    sentiment = classification_result.get("sentiment")

    from_email = msg.get("From", "")

    reply = Reply(
        campaign_id=campaign.id,
        raw_text=body[:10000],
        classification=classification,
        sentiment=sentiment,
        imap_message_id=imap_message_id,
        from_email=from_email,
        received_at=datetime.now(timezone.utc),
    )
    db.add(reply)
    await db.commit()
    logger.info(
        "Reply stored: campaign=%s classification=%s sentiment=%s",
        campaign_id, classification, sentiment,
    )


# ── Background polling loop ───────────────────────────────────────────────────

async def poll_forever() -> None:
    """
    Background task: poll inbox every IMAP_POLL_INTERVAL_SECONDS.
    Started once at FastAPI lifespan startup. Never blocks the API.
    """
    if not settings.IMAP_USER or not settings.IMAP_PASSWORD:
        logger.info("IMAP not configured (IMAP_USER/IMAP_PASSWORD empty). Reply poller disabled.")
        return

    logger.info(
        "Reply poller started. Polling every %ds.", settings.IMAP_POLL_INTERVAL_SECONDS
    )
    while True:
        try:
            client = await _connect_imap()
            uids = await _fetch_unseen_uids(client)
            logger.info("Reply poller: %d unseen message(s) found.", len(uids))

            async with AsyncSessionLocal() as db:
                for uid in uids:
                    msg = await _fetch_message(client, uid)
                    if msg:
                        await _process_message(msg, db)

            await client.logout()
        except Exception as exc:
            logger.error("Reply poller error: %s", exc)

        await asyncio.sleep(settings.IMAP_POLL_INTERVAL_SECONDS)
