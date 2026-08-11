# B2B Outreach Platform MVP

A single-tenant, semi-automated B2B outreach tool. It bridges a local Google Maps scraper (Jupyter notebook) with an AI-powered pipeline to enrich, score, draft, and track emails.

## Architecture

* **Module 1 (Discovery)**: `Business_scraper.ipynb`. Scrapes Google Maps leads and dumps them into a Google Sheet.
* **Backend (FastAPI)**: Connects to Postgres. Handles Module 2 (Enrichment), Modules 3+4 (Scoring), Module 5 (Persona), Module 6 (Drafting), Module 8 (Sending), and Module 9 (Reply Polling). 
* **Frontend (Next.js)**: A CRM dashboard and human-in-the-loop review queue for sending emails (Module 7, 10).

## Prerequisites

1. Python 3.10+
2. Node.js 18+
3. Docker & Docker Compose (for PostgreSQL)

## Setup Instructions

### 1. Database
```bash
docker-compose up -d
```

### 2. Backend (FastAPI)
```bash
cd backend
python -m venv venv
# On Windows: .\venv\Scripts\activate
# On Mac/Linux: source venv/bin/activate

pip install -r requirements.txt

# Create .env from example
cp .env.example .env
# Edit .env and insert your API keys (Gemini, SendGrid, IMAP)

# Apply database migrations
alembic upgrade head

# Start the server
uvicorn backend.main:app --reload --port 8000
```
*(Note: If you are on Windows and lack C++ Build Tools, you may need to install them to compile asyncpg or greenlet during `pip install`.)*

### 3. Frontend (Next.js)
```bash
cd frontend
npm install
npm run dev
```
Dashboard available at: `http://localhost:3000`

## Compliance & Safeguards

This MVP enforces strict sending constraints:
- **No autonomous sending**: All emails require explicit human approval via the `/review` page.
- **Suppression List**: Every outgoing email checks the suppression list first.
- **Unsubscribe Link**: Every email contains a mandatory, cryptographically signed `{{unsubscribe_link}}`.
- **Daily Cap**: Hard-capped at 2,000 sent emails per calendar day (checked from DB).
- **Hourly Cap**: Token-bucket rate limited to 100 per hour.
- **Scraping**: The enrichment module strictly checks and respects `robots.txt` before parsing pages. Null fields are preserved; the LLM is explicitly prompted not to hallucinate missing data.

## Running Tests
```bash
cd backend
pytest tests/
```
