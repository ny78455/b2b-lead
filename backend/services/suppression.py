"""
services/suppression.py — Suppression list management

Every email send MUST call is_suppressed() first.
Suppression entries are added on:
  - Unsubscribe link clicks (via /api/unsubscribe endpoint)
  - Bounce notifications (future)
  - Manual additions
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import SuppressionEntry

logger = logging.getLogger(__name__)


class SuppressionError(Exception):
    """Raised when attempting to send to a suppressed email address."""
    pass


async def is_suppressed(email: str, db: AsyncSession) -> bool:
    """Return True if the email is on the suppression list."""
    email_lower = email.strip().lower()
    result = await db.execute(
        select(SuppressionEntry).where(SuppressionEntry.email == email_lower)
    )
    return result.scalar_one_or_none() is not None


async def add_to_suppression(email: str, reason: str, db: AsyncSession) -> SuppressionEntry:
    """Add an email to the suppression list. Idempotent — no error if already exists."""
    email_lower = email.strip().lower()

    # Check if already suppressed
    result = await db.execute(
        select(SuppressionEntry).where(SuppressionEntry.email == email_lower)
    )
    existing = result.scalar_one_or_none()
    if existing:
        logger.info("Email %s already on suppression list.", email_lower)
        return existing

    entry = SuppressionEntry(email=email_lower, reason=reason)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    logger.info("Added %s to suppression list (reason: %s).", email_lower, reason)
    return entry
