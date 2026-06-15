import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=api_key)


def generate_nudge(goals: dict, wins: list[str], name: str = "Friend") -> str:
    """
    Generate a personalized motivational message based on user's goals and wins.

    goals: dict with keys 'long_term', 'mid_term', 'short_term'
    wins: list of strings describing past achievements
    name: user's first name for personalized greeting
    """
    wins_text = "\n".join(f"- {w}" for w in wins) if wins else "- (no wins logged yet)"

    prompt = f"""You are a warm, motivational coach for an app called Nudge by Addicoot.

User's name: {name}

User's goals:
- Long term: {goals.get('long_term', 'Not set')}
- Mid term: {goals.get('mid_term', 'Not set')}
- Short term: {goals.get('short_term', 'Not set')}

User's past wins:
{wins_text}

Write a WhatsApp message with EXACTLY these 5 sections in order. 
No markdown. No asterisks. No bold. Use emojis naturally. Keep it warm and personal, not corporate.

Section 1 - Greeting: Start with a good morning greeting using their name. One line.

Section 2 - Goal Reminder: Remind them of ONE of their goals (pick the most relevant one for today). One or two lines.

Section 3 - Past Win Callout: Reference ONE specific past win to remind them they are capable. One or two lines.

Section 4 - Today's Action: Give ONE specific, concrete action they can take today toward their goal. Make it small and doable. One or two lines.

Section 5 - Closing: End with a short punchy motivational line. One line.

Separate each section with a blank line.
Do not use any labels or headers like "Section 1" — just write the message naturally.
Total message should feel like it came from a supportive friend, not a bot.
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
    print(generate_nudge(goals, wins, name="Shruthi"))