import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY not found. Check your .env file.")

supabase = create_client(url, key)

# --- 1. Create a test user (or get existing) ---
test_email = "shruthi@example.com"

existing = supabase.table("users").select("*").eq("email", test_email).execute()

if existing.data:
    user = existing.data[0]
    print("User already exists:", user["id"])
else:
    result = supabase.table("users").insert({"email": test_email}).execute()
    user = result.data[0]
    print("Created user:", user["id"])

user_id = user["id"]

# --- 2. Add some goals (only if none exist yet) ---
existing_goals = supabase.table("goals").select("*").eq("user_id", user_id).execute()

if not existing_goals.data:
    supabase.table("goals").insert([
        {"user_id": user_id, "goal_type": "long_term", "description": "Get a Data Analyst job by Oct 2026"},
        {"user_id": user_id, "goal_type": "mid_term", "description": "Complete 3 interviews this month"},
        {"user_id": user_id, "goal_type": "short_term", "description": "Apply to 5 jobs this week"},
    ]).execute()
    print("Inserted goals")
else:
    print("Goals already exist")

# --- 3. Add some wins (only if none exist yet) ---
existing_wins = supabase.table("wins").select("*").eq("user_id", user_id).execute()

if not existing_wins.data:
    supabase.table("wins").insert([
        {"user_id": user_id, "description": "Completed BQ26 certification"},
        {"user_id": user_id, "description": "Reached 500 LinkedIn followers"},
    ]).execute()
    print("Inserted wins")
else:
    print("Wins already exist")

# --- 4. Read everything back ---
print("\n=== Goals ===")
goals_data = supabase.table("goals").select("*").eq("user_id", user_id).execute()
for g in goals_data.data:
    print(f"- [{g['goal_type']}] {g['description']}")

print("\n=== Wins ===")
wins_data = supabase.table("wins").select("*").eq("user_id", user_id).execute()
for w in wins_data.data:
    print(f"- {w['description']}")