import asyncio
from backend.database import SessionLocal
from backend.models import Campaign
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()).limit(1))
        campaign = res.scalar_one_or_none()
        if campaign:
            print("--- DRAFT HTML START ---")
            print(repr(campaign.draft_html))
            print("--- DRAFT HTML END ---")
        else:
            print("No campaign found.")

asyncio.run(main())
