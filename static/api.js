// Nudge — shared API helper
// Loaded by every page that talks to the backend.

const NUDGE_API_BASE = "https://nudge-39yh.onrender.com";

const NudgeAPI = (function () {
  function getToken() {
    return localStorage.getItem("nudge_token");
  }

  function setSession(token, user) {
    localStorage.setItem("nudge_token", token);
    localStorage.setItem("nudge_user", JSON.stringify(user));
  }

  function getUser() {
    const raw = localStorage.getItem("nudge_user");
    return raw ? JSON.parse(raw) : null;
  }

  function clearSession() {
    localStorage.removeItem("nudge_token");
    localStorage.removeItem("nudge_user");
  }

  function isLoggedIn() {
    return !!getToken();
  }

  // Core request helper. Throws an Error with a human-readable message on failure.
  async function request(path, { method = "GET", body, auth = false } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (auth) {
      const token = getToken();
      if (!token) {
        throw new Error("Not signed in. Please log in again.");
      }
      headers["Authorization"] = `Bearer ${token}`;
    }

    let res;
    try {
      res = await fetch(`${NUDGE_API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (networkErr) {
      // Render free tier can be asleep — first request can take 30-50s to wake up.
      throw new Error(
        "Couldn't reach the server. It may be waking up — please try again in a moment."
      );
    }

    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      // no JSON body
    }

    if (!res.ok) {
      const detail = (data && data.detail) || `Request failed (${res.status})`;
      throw new Error(detail);
    }

    return data;
  }

  // --- Auth ---
  async function signup({ email, name, whatsapp_number, password }) {
    const data = await request("/signup", {
      method: "POST",
      body: { email, name, whatsapp_number, password },
    });
    setSession(data.token, data.user);
    return data;
  }

  async function login({ email, password }) {
    const data = await request("/login", {
      method: "POST",
      body: { email, password },
    });
    setSession(data.token, data.user);
    return data;
  }

  async function me() {
    const data = await request("/me", { auth: true });
    return data.user;
  }

  function logout() {
    clearSession();
  }

  // --- Goals ---
  async function getGoals(email) {
    const data = await request(`/goals/${encodeURIComponent(email)}`);
    return data.goals;
  }

  async function addGoal({ email, goal_type, description }) {
    const data = await request("/goals", {
      method: "POST",
      body: { email, goal_type, description },
    });
    return data.goal;
  }

  async function setPrimaryGoal({ goal_id, email }) {
    const data = await request(
      `/goals/${encodeURIComponent(goal_id)}/set-primary?email=${encodeURIComponent(email)}`,
      { method: "POST" }
    );
    return data.goal;
  }

  // --- Wins ---
  async function getWins(email) {
    const data = await request(`/wins/${encodeURIComponent(email)}`);
    return data.wins;
  }

  async function addWin({ email, description, goal_id }) {
    const data = await request("/wins", {
      method: "POST",
      body: { email, description, goal_id: goal_id || null },
    });
    return data.win;
  }

  // --- Nudge ---
  async function getNudge(email) {
    const data = await request(`/nudge/${encodeURIComponent(email)}`);
    return data.nudge;
  }

  // --- Check-ins ---
  async function getStreak(email) {
    const data = await request(`/check-ins/${encodeURIComponent(email)}/streak`);
    return data.streak;
  }

  async function getCheckInWeek(email) {
    const data = await request(`/check-ins/${encodeURIComponent(email)}/week`);
    return data.days;
  }

  async function manualCheckIn(email) {
    const data = await request("/check-ins/manual", {
      method: "POST",
      body: { email },
    });
    return data; // { message, already_checked_in }
  }

  async function undoCheckIn(email) {
    const data = await request("/check-ins/manual", {
      method: "DELETE",
      body: { email },
    });
    return data;
  }

  // --- Profile ---
  async function updateProfile({ email, name, whatsapp_number, delivery_time }) {
    const body = { email };
    if (name !== undefined) body.name = name;
    if (whatsapp_number !== undefined) body.whatsapp_number = whatsapp_number;
    if (delivery_time !== undefined) body.delivery_time = delivery_time;

    const data = await request(`/users/${encodeURIComponent(email)}`, {
      method: "PUT",
      body,
    });
    setSession(getToken(), data.user); // refresh cached user with new details
    return data.user;
  }

  async function deleteAccount(email) {
    const data = await request(`/users/${encodeURIComponent(email)}`, {
      method: "DELETE",
    });
    clearSession();
    return data;
  }

  return {
    getToken,
    getUser,
    isLoggedIn,
    logout,
    signup,
    login,
    me,
    getGoals,
    addGoal,
    setPrimaryGoal,
    getWins,
    addWin,
    getNudge,
    getStreak,
    getCheckInWeek,
    manualCheckIn,
    undoCheckIn,
    updateProfile,
    deleteAccount,
  };
})();