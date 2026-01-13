import os
import re
import asyncio
import requests
from datetime import datetime, timedelta
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ================== CONFIG ================== #

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

CHECK_INTERVAL_MINUTES = 5
POSTED_FILE = "posted_jobs.txt"

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is not set")
if not GROUP_CHAT_ID:
    raise RuntimeError("❌ GROUP_CHAT_ID is not set")
if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
    raise RuntimeError("❌ Adzuna API keys are not set")
if not SERPAPI_KEY:
    raise RuntimeError("❌ SERPAPI_KEY is not set")

GROUP_CHAT_ID = int(GROUP_CHAT_ID)
bot = Bot(token=BOT_TOKEN)


# ================== HELPERS ================== #

def load_posted_jobs():
    try:
        with open(POSTED_FILE, "r") as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()


def save_posted_job(job_id):
    with open(POSTED_FILE, "a") as f:
        f.write(job_id + "\n")


# ================== INFERENCE ================== #

def extract_experience(text):
    if not text:
        return None
    text = text.lower()

    patterns = [
        r'(\d+)\s*[-–to]+\s*(\d+)\s*years',
        r'(\d+)\+?\s*years',
        r'at least\s+(\d+)\s+years',
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(0) + " (estimated)"

    if "senior" in text:
        return "5+ years (estimated)"
    if "junior" in text or "entry level" in text:
        return "0–2 years (estimated)"

    return None


def extract_salary(text):
    if not text:
        return None

    m = re.search(r'\$\d{2,3}k\s*[-–to]+\s*\$\d{2,3}k', text, re.IGNORECASE)
    if m:
        return m.group(0)

    m = re.search(r'\$\d{4,6}', text)
    if m:
        return m.group(0)

    return None


def detect_h1b(text):
    if not text:
        return "Not mentioned"

    text = text.lower()
    keywords = ["visa sponsorship", "h1b", "work visa", "sponsorship"]

    return "Mentioned" if any(k in text for k in keywords) else "Not mentioned"


# ================== POSTING ================== #

async def post_job(job):
    desc = job.get("summary", "")

    msg = (
        f"📌 *{job['title']}*\n\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"🌐 Source: {job['source']}\n\n"
        f"💼 Experience: {extract_experience(desc) or 'Not specified'}\n"
        f"💰 Salary: {extract_salary(desc) or 'Not disclosed'}\n"
        f"🇺🇸 H1B Sponsorship: {detect_h1b(desc)}\n\n"
        f"📝 {desc[:700]}\n\n"
        f"🔗 [Apply Here]({job['url']})"
    )

    await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=msg,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


# ================== FETCHERS ================== #

def fetch_adzuna_jobs():
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": "data analyst",
        "where": "United States",
        "results_per_page": 20,
        "sort_by": "date"
    }

    res = requests.get(url, params=params, timeout=20).json()
    jobs = []

    for j in res.get("results", []):
        jobs.append({
            "id": str(j["id"]),
            "title": j["title"],
            "company": j["company"]["display_name"],
            "location": j["location"]["display_name"],
            "summary": j.get("description", ""),
            "url": j["redirect_url"],
            "source": "Adzuna"
        })

    return jobs


def fetch_google_jobs():
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_jobs",
        "q": "Data Analyst jobs USA",
        "hl": "en",
        "api_key": SERPAPI_KEY
    }

    res = requests.get(url, params=params, timeout=20).json()
    jobs = []

    for j in res.get("jobs_results", []):
        apply = j.get("apply_options", [])
        if not apply:
            continue

        jobs.append({
            "id": j.get("job_id") or j["title"] + j["company_name"],
            "title": j["title"],
            "company": j["company_name"],
            "location": j.get("location", "United States"),
            "summary": j.get("description", ""),
            "url": apply[0].get("link"),
            "source": j.get("via", "Google Jobs")
        })

    return jobs


# ================== MAIN LOGIC ================== #

async def check_and_post_new_jobs():
    print("🔍 Checking for new jobs...")
    posted = load_posted_jobs()

    jobs = fetch_adzuna_jobs() + fetch_google_jobs()
    new_jobs = [j for j in jobs if j["id"] not in posted]

    if not new_jobs:
        print("⏸ No new jobs")
        return

    for job in new_jobs:
        await post_job(job)
        save_posted_job(job["id"])
        print(f"✅ Posted: {job['title']}")


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_post_new_jobs, "interval", minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()

    print(f"🤖 Bot running (checks every {CHECK_INTERVAL_MINUTES} min)")
    await asyncio.Event().wait()


asyncio.run(main())

