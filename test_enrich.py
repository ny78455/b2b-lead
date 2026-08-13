import asyncio
import uuid
import logging
from backend.database import AsyncSessionLocal
from backend.routers.enrich import _run_full_pipeline

logging.basicConfig(level=logging.DEBUG)

async def check():
    async with AsyncSessionLocal() as db:
        res = await _run_full_pipeline('c5b00af1-d420-41db-9f3b-ee59b44edb61', db)
        print(f"Result: {res.status}, {res.message}")

if __name__ == "__main__":
    asyncio.run(check())
