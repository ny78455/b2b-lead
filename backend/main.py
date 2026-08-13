"""
main.py — FastAPI application entrypoint.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback

from backend.routers import leads, enrich, campaigns, replies, sync, scrape, bulk
from backend.services.reply_poller import poll_forever

import urllib.request
import email.utils
import datetime
import google.auth._helpers

def patch_google_auth_time():
    try:
        r = urllib.request.urlopen('http://www.google.com', timeout=3)
        real_time = email.utils.parsedate_to_datetime(r.headers['Date']).replace(tzinfo=None)
        offset = real_time - datetime.datetime.utcnow()
        orig = google.auth._helpers.utcnow
        google.auth._helpers.utcnow = lambda: orig() + offset
        print(f"Patched Google auth time. Offset: {offset}")
    except Exception as e:
        print(f"Failed to patch Google auth time: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply auth time patch to fix invalid_grant due to system clock drift
    patch_google_auth_time()
    
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

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # Ensure CORS headers are attached even on 500 crashes (like DB connection failures)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"}
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
app.include_router(scrape.router)
app.include_router(bulk.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
