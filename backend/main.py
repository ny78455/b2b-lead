"""
main.py — FastAPI application entrypoint.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import leads, enrich, campaigns, replies, sync
from backend.services.reply_poller import poll_forever


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start IMAP reply poller in the background
    poller_task = asyncio.create_task(poll_forever())
    yield
    # Shutdown: Cancel background tasks
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="B2B Outreach MVP API",
    version="0.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router)
app.include_router(enrich.router)
app.include_router(campaigns.router)
app.include_router(replies.router)
app.include_router(sync.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
