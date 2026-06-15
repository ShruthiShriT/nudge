import os
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from supabase import create_client
from nudge_engine import generate_nudge
import pytz
import logging

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


def send_daily_nudges():
    logger.info("⏰ Scheduler triggered — sending daily nudges...")

    # Fetch all users
    users = supabase.table("users").select("*").execute().data

    if not users:
        logger.info("No users found.")
        return

    for user in users:
        try:
            user_id = user["id"]
            email = user["email"]
            name = user.get("name") or "Friend"
            whatsapp = user.get("whatsapp_number") or "N/A"

            # Fetch goals
            goals_data = supabase.table("goals").select("*").eq("user_id", user_id).execute().data
            goals = {g["goal_type"]: g["description"] for g in goals_data}

            if not goals:
                logger.info(f"⚠️  Skipping {email} — no goals set")
                continue

            # Fetch wins
            wins_data = supabase.table("wins").select("*").eq("user_id", user_id).execute().data
            wins = [w["description"] for w in wins_data]

            # Generate nudge
            message = generate_nudge(goals, wins, name=name)

            # Save to daily_messages
            supabase.table("daily_messages").insert({
                "user_id": user_id,
                "message": message
            }).execute()

            # TODO: Replace this print with whatsapp_send(whatsapp, message) once Meta is ready
            logger.info(f"📱 Nudge for {name} ({whatsapp}):\n{message}\n{'-'*50}")

        except Exception as e:
            logger.error(f"❌ Error processing {user.get('email')}: {e}")

    logger.info("✅ Done sending nudges!")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(
        send_daily_nudges,
        trigger=CronTrigger(hour=8, minute=0, timezone=IST),
        id="daily_nudge",
        replace_existing=True
    )
    scheduler.start()
    logger.info("🗓️  Scheduler started — nudges will fire at 8:00 AM IST daily")
    return scheduler