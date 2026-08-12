# Cell 1
!pip install playwright gspread google-auth nest_asyncio
!playwright install-deps
!playwright install chromium
# Cell 2
from google.colab import files
import os

print("Please upload your credentials.json file:")
uploaded = files.upload()

# Rename the uploaded file to ensure it matches what the script expects
for filename in uploaded.keys():
    os.rename(filename, 'credentials.json')
    print("Credentials uploaded and ready!")
# Cell 3
import asyncio
import random
import urllib.parse
import gspread
import re
import json
import os
from playwright.async_api import async_playwright
import nest_asyncio
from tqdm.notebook import tqdm

nest_asyncio.apply()

# ==========================================
# CONFIGURATION
# ==========================================
QUERIES_FILE = "queries.json" # Now pointing to your JSON file
SPREADSHEET_NAME = "Google Maps Leads"
CREDENTIALS_FILE = "credentials.json"
MAX_RESULTS_WITH_EMAIL = 35 # Target number of successful email leads per query

async def human_delay(min_sec=2.0, max_sec=4.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

def load_queries():
    """Loads search queries from a JSON file. Creates a template if missing."""
    if not os.path.exists(QUERIES_FILE):
        print(f"'{QUERIES_FILE}' not found. Creating a default template...")
        default_queries = ["Plumbers in Austin, TX", "Roofers in Sydney, Australia"]
        with open(QUERIES_FILE, 'w') as f:
            json.dump(default_queries, f, indent=4)
        return default_queries

    try:
        with open(QUERIES_FILE, 'r') as f:
            queries = json.load(f)
            if not isinstance(queries, list) or not queries:
                print(f"Warning: '{QUERIES_FILE}' is empty or not a valid list format.")
                return []
            return queries
    except json.JSONDecodeError:
        print(f"Error: '{QUERIES_FILE}' contains invalid JSON formatting. Please check the file.")
        return []

def setup_google_sheets():
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        sh = gc.open(SPREADSHEET_NAME)
        worksheet = sh.sheet1

        all_values = worksheet.get_all_values()

        if not all_values:
            worksheet.append_row(["Search Query", "Business Name", "Phone Number", "Email", "Website URL", "Address", "Google Maps URL"])
            return worksheet, set(), {}

        # Build resume state
        existing_urls = set()
        query_success_counts = {}

        # Skip header row and analyze existing data
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
        print(f"Error connecting to Google Sheets: {e}")
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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
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

    # Email extraction logic
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

async def run_scraper():
    # Load queries from the JSON file first
    search_queries = load_queries()
    if not search_queries:
        print("No queries found. Exiting scraper.")
        return

    worksheet, existing_urls, query_success_counts = setup_google_sheets()
    if not worksheet:
        return

    print(f"Loaded {len(existing_urls)} previously scraped leads from Google Sheets. Resuming...\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US'
        )
        page = await context.new_page()

        # Loop through the queries loaded from JSON
        for query in search_queries:
            current_successes = query_success_counts.get(query, 0)
            target_needed = MAX_RESULTS_WITH_EMAIL - current_successes

            print(f"\n==========================================")
            print(f"Query: {query}")

            if target_needed <= 0:
                print(f"Already have {current_successes} leads with emails for this query. Skipping.")
                print(f"==========================================")
                continue

            print(f"Need {target_needed} more leads with emails.")
            print(f"==========================================")

            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://www.google.com/maps/search/{encoded_query}"

            await page.goto(search_url, wait_until="domcontentloaded")
            await human_delay(2, 4)

            try:
                consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("I agree")')
                if await consent_buttons.count() > 0:
                    await consent_buttons.first.click()
                    await human_delay(2, 3)
            except Exception:
                pass

            print("Loading results feed...")
            try:
                await page.wait_for_selector('div[role="feed"]', timeout=20000)
            except Exception:
                print("Could not find results feed. Skipping to next query.")
                continue

            print("Deep scrolling to build a large pool of URLs...")
            feed_locator = page.locator('div[role="feed"]')
            await feed_locator.hover()

            # Scrolled more times (12) to ensure we have enough buffer to account for businesses without emails
            for _ in range(12):
                await page.mouse.wheel(0, 2500)
                await human_delay(1.5, 2.5)

            links = await page.locator('a[href*="/maps/place/"]').all()
            urls_to_check = []
            for link in links:
                href = await link.get_attribute('href')
                if href and href not in existing_urls and href not in urls_to_check:
                    urls_to_check.append(href)

            print(f"Gathered {len(urls_to_check)} un-scraped URLs. Hunting for emails...")

            progress_bar = tqdm(total=target_needed, desc=f"Finding Emails for {query}")

            for url in urls_to_check:
                if target_needed <= 0:
                    break # We hit our target!

                extracted = await extract_business_data(page, url)
                existing_urls.add(url) # Add to memory so we don't scrape it again next run

                # RULE 1: Only save if email is found
                if extracted["email"] != "N/A" and extracted["name"] != "N/A":
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
                    progress_bar.update(1)

                await human_delay(1.5, 3)

            progress_bar.close()

            if target_needed > 0:
                print(f"Ran out of URLs for '{query}'. Still needed {target_needed} more emails.")

        print("\nAll scraping operations complete.")
        await browser.close()

await run_scraper()
