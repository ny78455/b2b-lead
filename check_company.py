import asyncio
import uuid
from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models import Company

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Company).where(Company.id == uuid.UUID('c5b00af1-d420-41db-9f3b-ee59b44edb61')))
        c = res.scalar_one_or_none()
        if c:
            print(f"Website: {c.website}")
            print(f"Enrichment Status: {c.enrichment_status}")
            print(f"Status: {c.status}")
            print(f"Persona: {bool(c.persona_summary)}")
        else:
            print("Not found")

if __name__ == "__main__":
    asyncio.run(check())
