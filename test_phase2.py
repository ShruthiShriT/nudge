"""
test_phase2.py — run this locally: python test_phase2.py

Tests everything in Phase 2 that does NOT require an approved WhatsApp
template or live Meta credentials:
  1. Nudge generation + save (existing pipeline, untouched)
  2. whatsapp_send() fails gracefully when creds/template aren't live (doesn't crash)
  3. Check-in insert + keyword matching logic
  4. Streak calculation

Run AFTER applying migrations_check_ins.sql in Supabase.
Requires .env with SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY already set.
WHATSAPP_* env vars are NOT required for this script — that's the point.
"""

import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

TEST_EMAIL = input("Enter the email of your existing test user: ").strip()


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- 1. Confirm test user + goals exist ---
section("1. Fetching test user")
user_result = supabase.table("users").select("*").eq("email", TEST_EMAIL).execute()
if not user_result.data:
    print(f"❌ No user found with email {TEST_EMAIL}. Aborting.")
    exit(1)

user = user_result.data[0]
user_id = user["id"]
print(f"✅ Found user: {user['name']} ({user_id})")
print(f"   whatsapp_number on file: {user.get('whatsapp_number')}")


# --- 2. Test nudge generation pipeline ---
section("2. Testing nudge generation (Gemini)")
from nudge_engine import generate_nudge

goals_data = supabase.table("goals").select("*").eq("user_id", user_id).execute().data
goals = {g["goal_type"]: g["description"] for g in goals_data}
wins_data = supabase.table("wins").select("*").eq("user_id", user_id).execute().data
wins = [w["description"] for w in wins_data]

if not goals:
    print("❌ Test user has no goals. Add a goal first via /goals endpoint.")
else:
    message = generate_nudge(goals, wins, name=user.get("name") or "Friend")
    print(f"✅ Nudge generated:\n{message}\n")


# --- 3. Test whatsapp_send() fails gracefully (no live creds expected) ---
section("3. Testing whatsapp_send() graceful failure")
from whatsapp_sender import whatsapp_send, WhatsAppSendError

try:
    whatsapp_send(user.get("whatsapp_number") or "919999999999", "test message")
    print("⚠️  whatsapp_send() succeeded — looks like creds/template ARE live!")
except WhatsAppSendError as e:
    print(f"✅ Failed as expected (template/creds not live yet): {e}")
except Exception as e:
    print(f"❌ Unexpected exception type (should be WhatsAppSendError): {type(e)} — {e}")


# --- 4. Test check-in insert + keyword matching ---
section("4. Testing check-in insert + keyword matching")

CHECK_IN_KEYWORDS = ["done", "✅", "yes", "finished", "completed", "did it"]

def is_check_in_reply(text: str) -> bool:
    lowered = text.strip().lower()
    return any(k in lowered for k in CHECK_IN_KEYWORDS)

test_messages = [
    ("Done! ✅", True),
    ("yep finished it", True),
    ("not yet, tomorrow", False),
    ("hello", False),
]

for msg, expected in test_messages:
    matched = is_check_in_reply(msg)
    status = "✅" if matched == expected else "❌"
    print(f"{status} '{msg}' -> matched={matched} (expected {expected})")

# Insert a real matched check-in for today to test streak calc
supabase.table("check_ins").insert({
    "user_id": user_id,
    "raw_message": "done ✅ (test insert)",
    "matched": True,
}).execute()
print("✅ Inserted a test check-in row for today")


# --- 5. Test streak calculation ---
section("5. Testing streak calculation")

result = (
    supabase.table("check_ins")
    .select("created_at")
    .eq("user_id", user_id)
    .eq("matched", True)
    .order("created_at", desc=True)
    .execute()
)

seen_dates = set()
for row in result.data:
    d = datetime.fromisoformat(row["created_at"]).date()
    seen_dates.add(d)

streak = 0
cursor = datetime.now(timezone.utc).date()
while cursor in seen_dates:
    streak += 1
    cursor -= timedelta(days=1)

print(f"✅ Current streak for {TEST_EMAIL}: {streak} day(s)")
print("\nNote: this should also match what GET /check-ins/{email}/streak returns")
print("once you run the FastAPI server and hit that endpoint directly.")

section("Phase 2 local test complete")
print("Everything above ran without needing WhatsApp template approval.")
print("Once the phone number + template are approved, re-run step 3")
print("(whatsapp_send) — it should succeed instead of raising an error.")
