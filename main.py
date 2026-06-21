import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
from nudge_engine import generate_nudge

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

app = FastAPI(title="Nudge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOKEN_EXPIRY_DAYS = 30
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# Simple keyword match for check-in detection. Case-insensitive, checked as substring.
CHECK_IN_KEYWORDS = ["done", "✅", "yes", "finished", "completed", "did it"]


# --- Request models ---
class CreateUserRequest(BaseModel):
    email: str
    name: str
    whatsapp_number: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GoalRequest(BaseModel):
    email: str
    goal_type: str  # long_term, mid_term, short_term
    description: str

class WinRequest(BaseModel):
    email: str
    description: str
    goal_id: str | None = None


# --- Helpers ---
def get_user(email: str) -> dict:
    result = supabase.table("users").select("*").eq("email", email).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    return result.data[0]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_DAYS)
    supabase.table("sessions").insert({
        "user_id": user_id,
        "token": token,
        "expires_at": expires_at.isoformat()
    }).execute()
    return token


def get_user_from_token(authorization: str = Header(None)) -> dict:
    """Use this as a dependency on routes that require login."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]

    result = supabase.table("sessions").select("*").eq("token", token).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    session = result.data[0]
    expires_at = datetime.fromisoformat(session["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")

    user_result = supabase.table("users").select("*").eq("id", session["user_id"]).execute()
    if not user_result.data:
        raise HTTPException(status_code=404, detail="User not found")
    return user_result.data[0]


# --- Endpoints ---

@app.get("/")
def root():
    return FileResponse("index.html")


@app.post("/signup")
def signup(req: CreateUserRequest):
    existing = supabase.table("users").select("*").eq("email", req.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    result = supabase.table("users").insert({
        "email": req.email,
        "name": req.name,
        "whatsapp_number": req.whatsapp_number,
        "password_hash": hash_password(req.password)
    }).execute()

    user = result.data[0]
    token = create_session(user["id"])
    user.pop("password_hash", None)
    return {"message": "Account created", "user": user, "token": token}


@app.post("/login")
def login(req: LoginRequest):
    result = supabase.table("users").select("*").eq("email", req.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = result.data[0]
    if not user.get("password_hash") or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_session(user["id"])
    user.pop("password_hash", None)
    return {"message": "Login successful", "user": user, "token": token}


@app.get("/me")
def get_me(user: dict = Depends(get_user_from_token)):
    user.pop("password_hash", None)
    return {"user": user}


# Keeping old /users endpoint for backward compatibility during transition.
# TODO: remove once onboarding/signup flow is fully wired to /signup
@app.post("/users")
def create_user(req: CreateUserRequest):
    existing = supabase.table("users").select("*").eq("email", req.email).execute()
    if existing.data:
        return {"message": "User already exists", "user": existing.data[0]}
    result = supabase.table("users").insert({
        "email": req.email,
        "name": req.name,
        "whatsapp_number": req.whatsapp_number,
        "password_hash": hash_password(req.password)
    }).execute()
    return {"message": "User created", "user": result.data[0]}


@app.post("/goals")
def add_goal(req: GoalRequest):
    if req.goal_type not in ["long_term", "mid_term", "short_term"]:
        raise HTTPException(status_code=400, detail="goal_type must be long_term, mid_term, or short_term")
    user = get_user(req.email)
    user_id = user["id"]

    existing_goals = supabase.table("goals").select("*").eq("user_id", user_id).execute()
    is_first_goal = len(existing_goals.data) == 0

    existing_of_type = supabase.table("goals").select("*").eq("user_id", user_id).eq("goal_type", req.goal_type).execute()

    if existing_of_type.data:
        result = supabase.table("goals").update({
            "description": req.description
        }).eq("user_id", user_id).eq("goal_type", req.goal_type).execute()
        return {"message": "Goal updated", "goal": result.data[0]}
    else:
        result = supabase.table("goals").insert({
            "user_id": user_id,
            "goal_type": req.goal_type,
            "description": req.description,
            "is_primary": is_first_goal
        }).execute()
        return {"message": "Goal added", "goal": result.data[0]}


@app.post("/goals/{goal_id}/set-primary")
def set_primary_goal(goal_id: str, email: str):
    """Mark one goal as primary; unmarks any other primary goal for this user."""
    user = get_user(email)
    user_id = user["id"]

    goal_check = supabase.table("goals").select("*").eq("id", goal_id).eq("user_id", user_id).execute()
    if not goal_check.data:
        raise HTTPException(status_code=404, detail="Goal not found for this user")

    supabase.table("goals").update({"is_primary": False}).eq("user_id", user_id).eq("is_primary", True).execute()
    result = supabase.table("goals").update({"is_primary": True}).eq("id", goal_id).execute()
    return {"message": "Primary goal updated", "goal": result.data[0]}


@app.get("/goals/{email}")
def get_goals(email: str):
    user = get_user(email)
    result = supabase.table("goals").select("*").eq("user_id", user["id"]).execute()
    return {"goals": result.data}


@app.post("/wins")
def add_win(req: WinRequest):
    user = get_user(req.email)
    user_id = user["id"]

    win_data = {
        "user_id": user_id,
        "description": req.description
    }

    if req.goal_id:
        goal_check = supabase.table("goals").select("*").eq("id", req.goal_id).eq("user_id", user_id).execute()
        if not goal_check.data:
            raise HTTPException(status_code=404, detail="Goal not found for this user")
        win_data["goal_id"] = req.goal_id

    result = supabase.table("wins").insert(win_data).execute()
    return {"message": "Win added", "win": result.data[0]}


@app.get("/wins/{email}")
def get_wins(email: str):
    user = get_user(email)
    result = supabase.table("wins").select("*").eq("user_id", user["id"]).order("created_at", desc=True).execute()
    return {"wins": result.data}


@app.get("/nudge/{email}")
def get_nudge(email: str):
    user = get_user(email)
    user_id = user["id"]
    name = user.get("name") or "Friend"

    goals_result = supabase.table("goals").select("*").eq("user_id", user_id).execute()
    goals = {}
    for g in goals_result.data:
        goals[g["goal_type"]] = g["description"]

    if not goals:
        raise HTTPException(status_code=400, detail="No goals found. Add goals first.")

    wins_result = supabase.table("wins").select("*").eq("user_id", user_id).execute()
    wins = [w["description"] for w in wins_result.data]

    message = generate_nudge(goals, wins, name=name)

    supabase.table("daily_messages").insert({
        "user_id": user_id,
        "message": message
    }).execute()

    return {"email": email, "nudge": message}


def get_user_by_whatsapp(whatsapp_number: str) -> dict | None:
    """Match an inbound WhatsApp number against stored users.whatsapp_number.
    Tries exact match first, then a loose suffix match (last 10 digits) to
    tolerate +91 vs no-plus vs spacing differences."""
    clean = whatsapp_number.strip().replace("+", "").replace(" ", "").replace("-", "")

    result = supabase.table("users").select("*").eq("whatsapp_number", clean).execute()
    if result.data:
        return result.data[0]

    result = supabase.table("users").select("*").eq("whatsapp_number", f"+{clean}").execute()
    if result.data:
        return result.data[0]

    # Loose fallback: match on last 10 digits in case formatting differs
    all_users = supabase.table("users").select("*").execute().data
    suffix = clean[-10:]
    for u in all_users:
        stored = (u.get("whatsapp_number") or "").replace("+", "").replace(" ", "").replace("-", "")
        if stored[-10:] == suffix and suffix:
            return u
    return None


def is_check_in_reply(text: str) -> bool:
    lowered = text.strip().lower()
    return any(keyword in lowered for keyword in CHECK_IN_KEYWORDS)


@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """Meta calls this once when you register the webhook URL in the App Dashboard.
    Query params come in as hub.mode / hub.verify_token / hub.challenge — dots aren't
    valid Python identifiers so we read them off request.query_params directly."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(content=challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    """Handles inbound WhatsApp messages (user replies). Detects check-in
    keywords and logs every inbound message to check_ins for streak tracking."""
    payload = await request.json()

    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Could be a status update (delivered/read) rather than a message — ignore
            return {"status": "ignored"}

        for msg in messages:
            from_number = msg.get("from", "")
            text = msg.get("text", {}).get("body", "")

            user = get_user_by_whatsapp(from_number)
            if not user:
                continue  # message from unknown number, skip

            matched = is_check_in_reply(text)
            supabase.table("check_ins").insert({
                "user_id": user["id"],
                "raw_message": text,
                "matched": matched,
            }).execute()

        return {"status": "ok"}

    except (IndexError, KeyError, AttributeError):
        # Malformed or unexpected payload shape — don't 500, just acknowledge
        return {"status": "ignored"}


@app.get("/check-ins/{email}/streak")
def get_check_in_streak(email: str):
    """Returns the user's current consecutive-day check-in streak, used by
    the dashboard's streak panel. A day counts if it has at least one
    matched=True check-in."""
    user = get_user(email)
    result = (
        supabase.table("check_ins")
        .select("created_at")
        .eq("user_id", user["id"])
        .eq("matched", True)
        .order("created_at", desc=True)
        .execute()
    )

    if not result.data:
        return {"email": email, "streak": 0}

    # Collect distinct dates (IST-naive, good enough for daily streaks) check-ins occurred on
    seen_dates = set()
    for row in result.data:
        d = datetime.fromisoformat(row["created_at"]).date()
        seen_dates.add(d)

    streak = 0
    cursor = datetime.now(timezone.utc).date()
    while cursor in seen_dates:
        streak += 1
        cursor = cursor - timedelta(days=1)

    return {"email": email, "streak": streak}


# Start scheduler when app starts
from scheduler import start_scheduler
start_scheduler()