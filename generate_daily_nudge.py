import os
from dotenv import load_dotenv
from supabase import create_client
from nudge_engine import generate_nudge

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)


def get_user_nudge(email: str) -> str:
    # 1. Find user
    user_result = supabase.table("users").select("*").eq("email", email).execute()
    if not user_result.data:
        raise ValueError(f"No user found with email {email}")
    user_id = user_result.data[0]["id"]

    # 2. Fetch goals
    goals_result = supabase.table("goals").select("*").eq("user_id", user_id).execute()
    goals = {}
    for g in goals_result.data:
        goals[g["goal_type"]] = g["description"]

    # 3. Fetch wins
    wins_result = supabase.table("wins").select("*").eq("user_id", user_id).execute()
    wins = [w["description"] for w in wins_result.data]

    # 4. Generate message
    message = generate_nudge(goals, wins)

    # 5. Save it to daily_messages (so we have history)
    supabase.table("daily_messages").insert({
        "user_id": user_id,
        "message": message
    }).execute()

    return message


if __name__ == "__main__":
    email = "shruthi@example.com"
    nudge = get_user_nudge(email)
    print(f"=== Today's Nudge for {email} ===")
    print(nudge)