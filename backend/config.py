"""
config.py — All settings loaded from .env / environment variables.

Copy .env.example → .env and fill in real values before running.
"""
import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://b2b_user:b2b_pass@localhost:5432/b2b"

    # ── LLM — Gemini API ──────────────────────────────────────────────────────
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"   # Gemini API model name

    # ── Email sending (Gmail SMTP) ─────────────────────────────────────────────
    # Use a Gmail App Password — NOT your regular account password.
    # Enable 2-Step Verification first, then create an App Password at:
    #   Google Account → Security → 2-Step Verification → App passwords
    GMAIL_USER: str = "your_email@gmail.com"
    GMAIL_APP_PASSWORD: str = ""          # 16-character App Password
    SENDER_NAME: str = "Your Name"
    SENDER_EMAIL: str = ""                # defaults to GMAIL_USER if left blank
    SENDER_COMPANY: str = "Your Company"
    CALENDAR_LINK: str = ""               # static calendar scheduling link

    # ── Unsubscribe ───────────────────────────────────────────────────────────
    UNSUBSCRIBE_BASE_URL: str = "http://localhost:8000"   # public-facing base URL

    # ── IMAP (reply detection) ────────────────────────────────────────────────
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_USER: str = ""
    IMAP_PASSWORD: str = ""                               # app-specific password for Gmail
    IMAP_FOLDER: str = "INBOX"
    IMAP_POLL_INTERVAL_SECONDS: int = 300                 # 5 minutes

    # ── Google Sheets (Module 1 staging area) ─────────────────────────────────
    GSPREAD_CREDENTIALS_FILE: str = str(BASE_DIR / "credentials.json")   # service-account JSON
    SPREADSHEET_NAME: str = "Google Maps Leads"

    # ── Volume caps ───────────────────────────────────────────────────────────
    DAILY_SEND_LIMIT: int = 2000      # hard ceiling on sent emails per calendar day
    HOURLY_SEND_LIMIT: int = 100      # token-bucket rate limiter ceiling
    ENRICH_DELAY_SECONDS: float = 1.0 # pause between batch enrichment jobs


@lru_cache
def get_settings() -> Settings:
    return Settings()
