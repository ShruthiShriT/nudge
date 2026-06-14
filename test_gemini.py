import os
from dotenv import load_dotenv
from google import genai

# Load API key from .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

client = genai.Client(api_key=api_key)

# Sample data - this is what will eventually come from the database
goals = {
    "long_term": "Get a Data Analyst job by Oct 2026",
    "mid_term": "Complete 3 interviews this month",
    "short_term": "Apply to 5 jobs this week"
}

wins = [
    "Completed BQ26 certification",
    "Reached 500 LinkedIn followers",
    "Finished a Python automation project"
]

prompt = f"""You are a motivational coach for an app called Nudge.

User's goals:
- Long term: {goals['long_term']}
- Mid term: {goals['mid_term']}
- Short term: {goals['short_term']}

User's past wins:
{chr(10).join(f"- {w}" for w in wins)}

Write a short (2-3 sentences), warm, motivational daily reminder.
Reference one of their past wins to build confidence, and connect it
to one of their goals. Keep it personal and encouraging, not generic.
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

print("=== Today's Nudge ===")
print(response.text)