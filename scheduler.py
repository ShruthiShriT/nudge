import os
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from supabase import create_client
from nudge_engine import generate_nudge
from whatsapp_sender import whatsapp_send, WhatsAppSendError
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
    """Runs every minute. Sends a nudge to users whose delivery_time
    matches the current HH:MM in their local time (stored as IST for now).
    Falls back to 08:00 if delivery_time is null."""
    now_ist = datetime.now(IST)
    current_hhmm = now_ist.strftime("%H:%M")
    logger.info(f"Scheduler tick — {current_hhmm} IST")

    users = supabase.table("users").select("*").execute().data
    if not users:
        return

    for user in users:
        try:
            delivery_time = user.get("delivery_time") or "08:00"

            # Normalize to HH:MM in case DB stored it with seconds e.g. "08:00:00"
            if len(delivery_time) > 5:
                delivery_time = delivery_time[:5]

            if delivery_time != current_hhmm:
                continue  # Not their send time yet

            user_id = user["id"]
            email = user["email"]
            name = user.get("name") or "Friend"
            whatsapp = user.get("whatsapp_number") or "N/A"

            goals_data = supabase.table("goals").select("*").eq("user_id", user_id).execute().data
            goals = {g["goal_type"]: g["description"] for g in goals_data}

            if not goals:
                logger.info(f"Skipping {email} — no goals set")
                continue

            wins_data = supabase.table("wins").select("*").eq("user_id", user_id).execute().data
            wins = [w["description"] for w in wins_data]

            message = generate_nudge(goals, wins, name=name)

            supabase.table("daily_messages").insert({
                "user_id": user_id,
                "message": message
            }).execute()

            if whatsapp == "N/A":
                logger.info(f"Skipping WhatsApp send for {email} — no number on file")
            else:
                try:
                    whatsapp_send(whatsapp, message)
                    logger.info(f"Sent nudge to {name} ({whatsapp}) at {current_hhmm}")
                except WhatsAppSendError as e:
                    logger.error(f"WhatsApp send failed for {name} ({whatsapp}): {e}")

        except Exception as e:
            logger.error(f"Error processing {user.get('email')}: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(
        send_daily_nudges,
        trigger=CronTrigger(minute="*", timezone=IST),  # every minute
        id="daily_nudge",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started — checking delivery times every minute")
    return scheduler