"""
services/scraper.py — Automated Google Maps Scraper (Background Service)

Connects to Google Sheets, scrapes Google Maps using Playwright,
extracts emails, and appends the results to the sheet.
"""
import asyncio
import random
import urllib.parse
import re
import logging
import gspread
from playwright.async_api import async_playwright

from backend.config import get_settings
from backend.models import Company, Contact
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_RESULTS_WITH_EMAIL = 10  # Kept lower for web request reasonable completion time, or can run in background
STOP_SCRAPING = False

async def human_delay(min_sec=1.5, max_sec=3.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

def setup_google_sheets():
    try:
        gc = gspread.service_account(filename=settings.GSPREAD_CREDENTIALS_FILE)
        sh = gc.open(settings.SPREADSHEET_NAME)
        worksheet = sh.sheet1
        
        all_values = worksheet.get_all_values()
        
        if not all_values:
            worksheet.append_row(["Search Query", "Business Name", "Phone Number", "Email", "Website URL", "Address", "Google Maps URL"])
            return worksheet, set(), {}
            
        existing_urls = set()
        query_success_counts = {}
        
        for row in all_values[1:]:
            if len(row) >= 7:
                query = row[0]
                maps_url = row[6]
                email = row[3]
                
                existing_urls.add(maps_url)
                if email and email != "N/A":
                    query_success_counts[query] = query_success_counts.get(query, 0) + 1
                    
        return worksheet, existing_urls, query_success_counts
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets: {e}")
        return None, set(), {}

async def extract_business_data(page, url):
    data = {
        "name": "N/A",
        "phone": "N/A",
        "email": "N/A",
        "website": "N/A",
        "address": "N/A",
        "url": url
    }
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_selector('h1', timeout=15000)
        await human_delay(1, 2)
    except Exception:
        pass

    try:
        name_locator = page.locator('h1')
        if await name_locator.count() > 0:
            data["name"] = await name_locator.first.inner_text()
    except Exception: pass

    try:
        address_locator = page.locator('button[data-item-id="address"] div.fontBodyMedium')
        if await address_locator.count() > 0:
            data["address"] = await address_locator.first.inner_text()
    except Exception: pass

    try:
        website_locator = page.locator('a[data-item-id="authority"] div.fontBodyMedium')
        if await website_locator.count() > 0:
            data["website"] = await website_locator.first.inner_text()
    except Exception: pass

    try:
        phone_locator = page.locator('button[data-item-id^="phone:tel:"] div.fontBodyMedium')
        if await phone_locator.count() > 0:
            data["phone"] = await phone_locator.first.inner_text()
    except Exception: pass

    if data["website"] != "N/A":
        try:
            target_url = data["website"]
            if not target_url.startswith("http"):
                target_url = "http://" + target_url

            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            page_content = await page.content()

            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            found_emails = set(re.findall(email_pattern, page_content))

            valid_emails = [
                email for email in found_emails
                if not email.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'))
                and "sentry" not in email
                and "example" not in email
            ]

            if valid_emails:
                data["email"] = valid_emails[0]
        except Exception:
            pass

    return data

async def run_scraper(search_queries: list[str], target_leads: int | None = None, timeout_minutes: int | None = None):
    global STOP_SCRAPING
    STOP_SCRAPING = False
    
    import time
    start_time = time.time()

    logger.info(f"Starting scraper for queries: {search_queries}")
    worksheet, existing_urls, query_success_counts = setup_google_sheets()
    if not worksheet:
        logger.error("Failed to setup Google Sheets. Aborting scrape.")
        return

    logger.info(f"Loaded {len(existing_urls)} previously scraped leads from Google Sheets.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US'
        )
        page = await context.new_page()

        if target_leads is not None:
            random.shuffle(search_queries)
            logger.info(f"Shuffled {len(search_queries)} queries for bulk scraping, targeting {target_leads} leads.")
        
        session_leads_gathered = 0

        for query in search_queries:
            if target_leads is not None and session_leads_gathered >= target_leads:
                logger.info(f"Reached global target of {target_leads} leads. Stopping scraper.")
                break
            if timeout_minutes is not None:
                elapsed_minutes = (time.time() - start_time) / 60
                if elapsed_minutes > timeout_minutes:
                    logger.info(f"Scraper timeout reached ({timeout_minutes} mins). Stopping.")
                    break

            if STOP_SCRAPING:
                logger.info("Scraping stopped by user.")
                break

            if target_leads is not None:
                # If target_leads is set, we still limit to 10 per query to spread them out, 
                # but we bound it by the global target remaining.
                target_needed = min(10, target_leads - session_leads_gathered)
            else:
                current_successes = query_success_counts.get(query, 0)
                target_needed = MAX_RESULTS_WITH_EMAIL - current_successes

            if target_needed <= 0:
                logger.info(f"Already have enough leads for '{query}' (or global target met). Skipping.")
                continue

            logger.info(f"Scraping '{query}', need {target_needed} more emails.")

            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/maps/search/{encoded_query}"

            try:
                await page.goto(search_url, wait_until="domcontentloaded")
                await human_delay(2, 4)
            except Exception as e:
                logger.error(f"Failed to navigate to search URL: {e}")
                continue

            try:
                consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("I agree")')
                if await consent_buttons.count() > 0:
                    await consent_buttons.first.click()
                    await human_delay(2, 3)
            except Exception:
                pass

            try:
                await page.wait_for_selector('div[role="feed"]', timeout=20000)
            except Exception:
                logger.info("Could not find results feed. Skipping.")
                continue

            feed_locator = page.locator('div[role="feed"]')
            await feed_locator.hover()

            # Scroll a few times to get a good pool
            for _ in range(5):
                await page.mouse.wheel(0, 2500)
                await human_delay(1.5, 2.5)

            links = await page.locator('a[href*="/maps/place/"]').all()
            urls_to_check = []
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    if href and href not in existing_urls and href not in urls_to_check:
                        urls_to_check.append(href)
                except Exception:
                    pass

            logger.info(f"Gathered {len(urls_to_check)} new URLs.")

            for url in urls_to_check:
                if timeout_minutes is not None:
                    if (time.time() - start_time) / 60 > timeout_minutes:
                        logger.info("Scraping stopped due to timeout during extraction.")
                        break

                if STOP_SCRAPING:
                    logger.info("Scraping stopped by user during extraction.")
                    break
                    
                if target_needed <= 0:
                    break

                extracted = await extract_business_data(page, url)
                existing_urls.add(url)

                if extracted["email"] != "N/A" and extracted["name"] != "N/A":
                    try:
                        worksheet.append_row([
                            query,
                            extracted["name"],
                            extracted["phone"],
                            extracted["email"],
                            extracted["website"],
                            extracted["address"],
                            extracted["url"]
                        ])
                        target_needed -= 1
                        session_leads_gathered += 1
                        logger.info(f"Saved: {extracted['name']} - {extracted['email']}")
                        
                        # We also auto-sync to DB immediately
                        await _sync_single_lead_to_db(query, extracted)
                    except Exception as e:
                        logger.error(f"Failed to append to Google Sheet: {e}")

                await human_delay(1.5, 3)

        await browser.close()
        logger.info("Scraping completed.")

async def _sync_single_lead_to_db(query, extracted):
    """
    Write the scraped lead into Postgres using a thread-local async engine.
    We must NOT reuse the global engine/session because this coroutine runs
    in the scraper's own ProactorEventLoop thread — asyncpg connections are
    bound to the event loop that created them.
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=0,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with session_factory() as db:
            email_val = extracted["email"].strip().lower()
            company_name = extracted["name"].strip()

            existing = await db.execute(select(Contact).where(Contact.email == email_val))
            if existing.scalar_one_or_none():
                return

            company = Company(
                name=company_name,
                website=extracted["website"] if extracted["website"] != "N/A" else None,
                phone=extracted["phone"] if extracted["phone"] != "N/A" else None,
                address=extracted["address"] if extracted["address"] != "N/A" else None,
                google_maps_url=extracted["url"],
                search_query=query,
                enrichment_status="pending",
                status="new",
            )
            db.add(company)
            await db.flush()

            contact = Contact(
                company_id=company.id,
                email=email_val,
                source="scraper",
                confidence="medium",
            )
            db.add(contact)
            await db.commit()
            logger.info(f"Synced to DB: {company_name} <{email_val}>")
    finally:
        await engine.dispose()
