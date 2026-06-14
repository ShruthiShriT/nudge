import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=api_key)


def generate_nudge(goals: dict, wins: list[str]) -> str:
    """
    Generate a personalized motivational message based on user's goals and wins.

    goals: dict with keys 'long_term', 'mid_term', 'short_term'
    wins: list of strings describing past achievements
    """
    wins_text = "\n".join(f"- {w}" for w in wins) if wins else "- (no wins logged yet)"

    prompt = f"""You are a motivational coach for an app called Nudge.

User's goals:
- Long term: {goals.get('long_term', 'Not set')}
- Mid term: {goals.get('mid_term', 'Not set')}
- Short term: {goals.get('short_term', 'Not set')}

User's past wins:
{wins_text}

Write a short (2-3 sentences), warm, motivational daily reminder.
Reference one of their past wins to build confidence, and connect it
to one of their goals. Keep it personal and encouraging, not generic.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text.strip()


if __name__ == "__main__":
    # quick manual test
    goals = {
        "long_term": "Get a Data Analyst job by Oct 2026",
        "mid_term": "Complete 3 interviews this month",
        "short_term": "Apply to 5 jobs this week"
    }
    wins = [
        "Completed BQ26 certification",
        "Reached 500 LinkedIn followers"
    ]

    print("=== Today's Nudge ===")
    print(generate_nudge(goals, wins))