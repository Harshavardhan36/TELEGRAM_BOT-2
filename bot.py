
import os
import asyncio
import requests
from datetime import datetime, timedelta
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ---------------- CONFIG ---------------- #
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

CHECK_INTERVAL_MINUTES = 5
POSTED_FILE = "posted_jobs.txt"

# ---- safety checks ---- #
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is not set")

if not GROUP_CHAT_ID:
    raise RuntimeError("❌ GROUP_CHAT_ID is not set")

if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
    raise RuntimeError("❌ Adzuna API keys are not set")

GROUP_CHAT_ID = int(GROUP_CHAT_ID)

bot = Bot(token=BOT_TOKEN)

# ---------------- FILTER LOGIC (SAFE) ---------------- #
H1B_KEYWORDS = ["h1b", "visa sponsorship", "work visa", "sponsor"]
OPT_KEYWORDS = ["opt", "cpt", "stem opt", "f1"]
CONTRACT_KEYWORDS = ["contract", "c2c", "1099", "contractor"]

# ---------------- HELPERS ---------------- #
def load_posted_jobs():
    try:
        with open(POSTED_FILE, "r") as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_posted_job(job_id):
    with open(POSTED_FILE, "a") as f:
        f.write(job_id + "\n")

# ---------------- FETCH JOBS ---------------- #
def fetch_data_analyst_jobs():
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": "data analyst",
        "where": "United States",
        "results_per_page": 20,
        "sort_by": "date"
    }

    res = requests.get(url, params=params)
    data = res.json()

    jobs = []
    last_2h = datetime.utcnow() - timedelta(hours=2)

    for j in data.get("results", []):
        job_id = j["id"]
        description = j.get("description", "").lower()
        created = datetime.fromisoformat(j["created"].replace("Z", ""))

        if created < last_2h:
            continue

        h1b = any(k in description for k in H1B_KEYWORDS)
        opt = any(k in description for k in OPT_KEYWORDS)

        if not (h1b or opt):
            continue

        job_type = "Contract" if any(k in description for k in CONTRACT_KEYWORDS) else "Full-Time"

        jobs.append({
            "id": job_id,
            "title": j["title"],
            "company": j["company"]["display_name"],
            "location": j["location"]["display_name"],
            "type": job_type,
            "h1b": "Yes" if h1b else "Possible",
            "opt": "Yes" if opt else "Possible",
            "url": j["redirect_url"]
        })

    return jobs

# ---------------- POST NEW JOBS ---------------- #
async def check_and_post_new_jobs():
    print("🔍 Checking for new jobs...")
    posted = load_posted_jobs()
    jobs = fetch_data_analyst_jobs()

    new_jobs = [j for j in jobs if j["id"] not in posted]

    if not new_jobs:
        print("⏸ No new jobs")
        return

    for job in new_jobs:
        msg = (
            f"🚨 *New Data Analyst Job Posted!* 🚨\n\n"
            f"*{job['title']}*\n"
            f"🏢 {job['company']}\n"
            f"📍 {job['location']}\n"
            f"🎓 OPT: {job['opt']}\n"
            f"🇺🇸 H1B: {job['h1b']}\n"
            f"💼 Type: {job['type']}\n"
            f"🔗 [Apply]({job['url']})"
        )

        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=msg,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

        save_posted_job(job["id"])
        print(f"✅ Posted: {job['title']}")

# ---------------- MAIN LOOP ---------------- #
async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_post_new_jobs,
        "interval",
        minutes=CHECK_INTERVAL_MINUTES
    )
    scheduler.start()

    print(f"🤖 Real-time bot running (checks every {CHECK_INTERVAL_MINUTES} min)")
    await asyncio.Event().wait()

asyncio.run(main())



