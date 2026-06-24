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
from fastapi.staticfiles import StaticFiles
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

class ManualCheckInRequest(BaseModel):
    email: str

class UpdateProfileRequest(BaseModel):
    email: str
    name: str | None = None
    whatsapp_number: str | None = None
    delivery_time: str | None = None  # 'HH:MM', 24-hour


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

app.mount("/static", StaticFiles(directory="static"), name="static")


def serve_page(filename: str):
    return FileResponse(f"static/{filename}")


@app.get("/")
def root():
    return serve_page("landing.html")

@app.get("/signin")
def signin_page():
    return serve_page("signin.html")

@app.get("/signup")
def signup_page():
    return serve_page("signup.html")

@app.get("/onboarding")
def onboarding_page():
    return serve_page("onboarding.html")

@app.get("/dashboard")
def dashboard_page():
    return serve_page("dashboard.html")

@app.get("/forgot-password")
def forgot_password_page():
    return serve_page("forgot-password.html")

@app.get("/reset-password")
def reset_password_page():
    return serve_page("reset-password.html")

@app.get("/api.js")
def api_js():
    return FileResponse("static/api.js", media_type="application/javascript")

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


@app.post("/check-ins/manual")
def manual_check_in(req: ManualCheckInRequest):
    """Lets a user mark today done from the dashboard, instead of only
    via WhatsApp reply. Inserts a matched=True row just like the webhook
    does, so it counts toward the streak the same way."""
    user = get_user(req.email)

    # Avoid double-counting if they already checked in today (manually
    # or via WhatsApp) — look for any matched check-in already today.
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    existing_today = (
        supabase.table("check_ins")
        .select("id")
        .eq("user_id", user["id"])
        .eq("matched", True)
        .gte("created_at", today_start.isoformat())
        .execute()
    )
    if existing_today.data:
        return {"message": "Already checked in today", "already_checked_in": True}

    supabase.table("check_ins").insert({
        "user_id": user["id"],
        "raw_message": "(marked done from dashboard)",
        "matched": True,
    }).execute()

    return {"message": "Checked in", "already_checked_in": False}

@app.delete("/check-ins/manual")
def undo_manual_check_in(req: ManualCheckInRequest):
    """Deletes today's manual dashboard check-in so the user can undo it.
    Only removes rows where raw_message is the dashboard marker — won't
    touch real WhatsApp check-ins."""
    user = get_user(req.email)

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    supabase.table("check_ins").delete().eq(
        "user_id", user["id"]
    ).eq(
        "raw_message", "(marked done from dashboard)"
    ).gte(
        "created_at", today_start.isoformat()
    ).execute()

    return {"message": "Check-in undone"}

@app.get("/check-ins/{email}/week")
def get_check_in_week(email: str):
    """Returns real per-day check-in data for the last 7 calendar days
    (today included), so the dashboard streak grid can show actual days
    instead of approximating from the single streak number."""
    user = get_user(email)

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = (
        supabase.table("check_ins")
        .select("created_at")
        .eq("user_id", user["id"])
        .eq("matched", True)
        .gte("created_at", seven_days_ago.isoformat())
        .execute()
    )

    done_dates = set()
    for row in result.data:
        d = datetime.fromisoformat(row["created_at"]).date()
        done_dates.add(d.isoformat())

    days = []
    today = datetime.now(timezone.utc).date()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        days.append({
            "date": d.isoformat(),
            "done": d.isoformat() in done_dates,
            "is_today": i == 0,
        })

    return {"email": email, "days": days}


@app.put("/users/{email}")
def update_profile(email: str, req: UpdateProfileRequest):
    """Lets a user edit name, WhatsApp number, and delivery time from
    the dashboard profile panel."""
    user = get_user(email)

    update_data = {}
    if req.name is not None:
        update_data["name"] = req.name
    if req.whatsapp_number is not None:
        update_data["whatsapp_number"] = req.whatsapp_number
    if req.delivery_time is not None:
        update_data["delivery_time"] = req.delivery_time

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("users").update(update_data).eq("id", user["id"]).execute()
    updated_user = result.data[0]
    updated_user.pop("password_hash", None)
    return {"message": "Profile updated", "user": updated_user}


@app.delete("/users/{email}")
def delete_account(email: str):
    """Permanently deletes a user and everything tied to them — goals,
    wins, check-ins, daily message history, and active sessions."""
    user = get_user(email)
    user_id = user["id"]

    supabase.table("goals").delete().eq("user_id", user_id).execute()
    supabase.table("wins").delete().eq("user_id", user_id).execute()
    supabase.table("check_ins").delete().eq("user_id", user_id).execute()
    supabase.table("daily_messages").delete().eq("user_id", user_id).execute()
    supabase.table("sessions").delete().eq("user_id", user_id).execute()
    supabase.table("users").delete().eq("id", user_id).execute()

    return {"message": "Account deleted"}


# Start scheduler when app starts
from scheduler import start_scheduler
start_scheduler()