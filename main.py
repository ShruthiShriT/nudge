import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
from nudge_engine import generate_nudge

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

app = FastAPI(title="Nudge API")

# Allow frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request models ---
class CreateUserRequest(BaseModel):
    email: str

class GoalRequest(BaseModel):
    email: str
    goal_type: str  # long_term, mid_term, short_term
    description: str

class WinRequest(BaseModel):
    email: str
    description: str


# --- Helper: get user id by email ---
def get_user_id(email: str) -> str:
    result = supabase.table("users").select("id").eq("email", email).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"User {email} not found")
    return result.data[0]["id"]


# --- Endpoints ---

@app.get("/")
def root():
    return {"message": "Nudge API is running"}


@app.post("/users")
def create_user(req: CreateUserRequest):
    existing = supabase.table("users").select("*").eq("email", req.email).execute()
    if existing.data:
        return {"message": "User already exists", "user": existing.data[0]}
    result = supabase.table("users").insert({"email": req.email}).execute()
    return {"message": "User created", "user": result.data[0]}


@app.post("/goals")
def add_goal(req: GoalRequest):
    if req.goal_type not in ["long_term", "mid_term", "short_term"]:
        raise HTTPException(status_code=400, detail="goal_type must be long_term, mid_term, or short_term")
    user_id = get_user_id(req.email)
    result = supabase.table("goals").insert({
        "user_id": user_id,
        "goal_type": req.goal_type,
        "description": req.description
    }).execute()
    return {"message": "Goal added", "goal": result.data[0]}


@app.post("/wins")
def add_win(req: WinRequest):
    user_id = get_user_id(req.email)
    result = supabase.table("wins").insert({
        "user_id": user_id,
        "description": req.description
    }).execute()
    return {"message": "Win added", "win": result.data[0]}


@app.get("/nudge/{email}")
def get_nudge(email: str):
    user_id = get_user_id(email)

    # Fetch goals
    goals_result = supabase.table("goals").select("*").eq("user_id", user_id).execute()
    goals = {}
    for g in goals_result.data:
        goals[g["goal_type"]] = g["description"]

    if not goals:
        raise HTTPException(status_code=400, detail="No goals found. Add goals first.")

    # Fetch wins
    wins_result = supabase.table("wins").select("*").eq("user_id", user_id).execute()
    wins = [w["description"] for w in wins_result.data]

    # Generate message
    message = generate_nudge(goals, wins)

    # Save to history
    supabase.table("daily_messages").insert({
        "user_id": user_id,
        "message": message
    }).execute()

    return {"email": email, "nudge": message}