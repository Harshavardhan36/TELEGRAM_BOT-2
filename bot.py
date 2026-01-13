import os
import csv
import asyncio
import requests
from datetime import datetime
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= CONFIG ================= #

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

CSV_FILE = "top_500_h1b_companies_ats_fallbacks.csv"
CHECK_INTERVAL_MINUTES = 5
POSTED_FILE = "posted_jobs.txt"

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is not set")
if not GROUP_CHAT_ID:
    raise RuntimeError("❌ GROUP_CHAT_ID is not set")
if not SERPAPI_KEY:
    raise RuntimeError("❌ SERPAPI_KEY is not set")

GROUP_CHAT_ID = int(GROUP_CHAT_ID)
bot = Bot(token=BOT_TOKEN)

# ================= ROLES ================= #

ROLE_QUERY = (
    '"Data Analyst" OR "Senior Data Analyst" OR "Business Analyst" OR '
    '"Business Intelligence Analyst" OR "BI Analyst" OR '
    '"Data Scientist" OR "Data Engineer" OR "Analytics Engineer" OR '
    '"Product Analyst" OR "Marketing Analyst" OR '
    '"Risk Analyst" OR "Quantitative Analyst" OR '
    '"Operations Analyst" OR "Supply Chain Analyst" OR '
    '"Quality Analyst" OR "Tableau Developer" OR "Power BI Developer"'
)

# ================= HELPERS ================= #

def load_posted_jobs():
    try:
        with open(POSTED_FILE, "r") as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_posted_job(job_id):
    with open(POSTED_FILE, "a") as f:
        f.write(job_id + "\n")

def load_companies():
    companies = []

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        required_company_col = "Company Name"
        url_columns = [
            "Primary Careers URL",
            "Workday URL",
            "Greenhouse URL",
            "Lever URL",
            "Jobs Page Fallback",
        ]

        if required_company_col not in reader.fieldnames:
            raise RuntimeError(
                f"❌ 'Company Name' column not found. Found: {reader.fieldnames}"
            )

        for row in reader:
            company = row[required_company_col].strip()
            if not company:
                continue

            sites = []
            for col in url_columns:
                val = row.get(col)
                if not val:
                    continue

                # split in case multiple URLs are in one cell
                for part in str(val).split("|"):
                    part = part.strip()
                    if part:
                        # remove protocol if present
                        part = part.replace("https://", "").replace("http://", "")
                        sites.append(part)

            if not sites:
                continue

            companies.append({
                "company": company,
                "sites": sites
            })

    print(f"✅ Loaded {len(companies)} companies with ATS fallbacks")
    return companies

def is_within_24_hours(posted_at: str) -> bool:
    if not posted_at:
        return False

    posted_at = posted_at.lower()

    if "minute" in posted_at:
        return True

    if "hour" in posted_at:
        try:
            hours = int(posted_at.split()[0])
            return hours <= 24
        except:
            return False

    if "day" in posted_at:
        return posted_at.startswith("1 day")

    return False

# ================= SERPAPI FETCH ================= #

def fetch_company_jobs(company, site):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_jobs",
        "q": f'site:{site} ({ROLE_QUERY})',
        "hl": "en",
        "api_key": SERPAPI_KEY,
        "tbs": "qdr:d"
    }

    try:
        res = requests.get(url, params=params, timeout=20).json()
    except Exception:
        return []

    jobs = []

    for j in res.get("jobs_results", []):
        posted_at = j.get("detected_extensions", {}).get("posted_at")
        if not is_within_24_hours(posted_at):
            continue

        apply_opts = j.get("apply_options", [])
        if not apply_opts:
            continue

        jobs.append({
            "id": j.get("job_id") or f"{company}-{j['title']}",
            "title": j["title"],
            "company": company,
            "location": j.get("location", "United States"),
            "summary": j.get("description", ""),
            "url": apply_opts[0].get("link"),
            "source": site,
            "posted": posted_at
        })

    return jobs

# ================= POSTING ================= #

async def post_job(job):
    msg = (
        f"📌 *{job['title']}*\n\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"🌐 Source: {job['source']}\n"
        f"⏱ Posted: {job['posted']}\n\n"
        f"📝 {job['summary'][:700]}\n\n"
        f"🔗 [Apply Here]({job['url']})"
    )

    await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=msg,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# ================= MAIN JOB LOOP ================= #

async def check_and_post_jobs():
    print("🔍 Checking for new jobs...")
    posted = load_posted_jobs()
    companies = load_companies()

    new_jobs = []

    for c in companies:
        for site in c["sites"]:
            jobs = fetch_company_jobs(c["company"], site)
            for job in jobs:
                if job["id"] not in posted:
                    new_jobs.append(job)

    if not new_jobs:
        print("⏸ No new jobs")
        return

    for job in new_jobs:
        await post_job(job)
        save_posted_job(job["id"])
        print(f"✅ Posted: {job['title']} ({job['company']})")

# ================= SCHEDULER ================= #

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_post_jobs,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES
    )
    scheduler.start()

    print(f"🤖 Bot running (checks every {CHECK_INTERVAL_MINUTES} minutes)")
    await asyncio.Event().wait()

asyncio.run(main())

