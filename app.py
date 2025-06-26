import streamlit as st
import requests, time, json

"""
BasicOps Forms Prototype – FINAL FIX
-----------------------------------
• Uses correct endpoints: /v1/project + /v1/task
• Robust token save / refresh
• Detailed error surfacing
"""

# ── CONFIG ───────────────────────────────────────────────
API_BASE     = "https://api.basicops.com/v1"
AUTH_URL     = "https://app.basicops.com/oauth/auth"
TOKEN_URL    = "https://api.basicops.com/oauth/token"
CLIENT_ID    = st.secrets["basicops_client_id"]
CLIENT_SEC   = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["basicops_redirect_uri"]

# ── PAGE SETUP ───────────────────────────────────────────
st.set_page_config("BasicOps Forms", layout="centered")
st.title("📝 BasicOps Task Form (OAuth)")

# ── SESSION HELPERS ─────────────────────────────────────

def save_tokens(tok: dict):
    st.session_state["access_token"]  = tok["access_token"]
    st.session_state["refresh_token"] = tok.get("refresh_token")
    st.session_state["expires_at"]    = time.time() + tok.get("expires_in", 3600) - 60  # 1‑min headroom

def token_valid() -> bool:
    return "access_token" in st.session_state and time.time() < st.session_state.get("expires_at", 0)

def refresh_token() -> bool:
    if "refresh_token" not in st.session_state:
        return False
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SEC,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "refresh_token",
        "refresh_token": st.session_state["refresh_token"],
    }, timeout=10)
    if r.ok:
        save_tokens(r.json())
        return True
    return False

# ── MINI WRAPPERS ───────────────────────────────────────

def ensure_token():
    if not token_valid() and not refresh_token():
        st.warning("Please connect to BasicOps again.")
        st.stop()


def api_get(path: str):
    ensure_token()
    url = f"{API_BASE}{path}"
    r = requests.get(url, headers={"Authorization": f"Bearer {st.session_state['access_token']}"}, timeout=10)
    if not r.ok:
        st.error(f"GET {path} → {r.status_code}\n{r.text[:300]}")
        st.stop()
    try:
        return r.json()
    except Exception:
        st.error("Response was not JSON (see below)")
        st.write(r.text[:1000])
        st.stop()


def api_post(path: str, payload: dict):
    ensure_token()
    r = requests.post(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {st.session_state['access_token']}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=10,
    )
    if not r.ok:
        st.error(f"POST {path} → {r.status_code}\n{r.text[:300]}")
        st.stop()
    return r.json()

# ── HANDLE ?code= ───────────────────────────────────────
if "code" in st.query_params and "access_token" not in st.session_state:
    code = st.query_params["code"]
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SEC,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
    }, timeout=10)
    if r.ok and r.json().get("access_token"):
        save_tokens(r.json())
        st.query_params.clear()
        st.rerun()
    else:
        st.error(f"Token exchange failed: {r.status_code}\n{r.text}")
        st.stop()

# ── LOGIN BUTTON ────────────────────────────────────────
if not token_valid():
    params = f"client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}"
    st.markdown(f"[🔑 Connect to BasicOps]({AUTH_URL}?{params})", unsafe_allow_html=True)
    st.stop()

st.success("Connected to BasicOps ✅")

# ── PROJECT PICKER ──────────────────────────────────────
proj_resp = api_get("/project?limit=100")
projects  = proj_resp.get("data", [])
if not projects:
    st.error("No projects returned. Check API scopes.")
    st.stop()

proj_map = {p["title"]: p["id"] for p in projects}
sel_name = st.selectbox("Select a Project", list(proj_map.keys()))
proj_id  = proj_map[sel_name]

# ── FORM ───────────────────────────────────────────────
with st.form("new_task"):
    task_title = st.text_input("Task title")
    task_notes = st.text_area("Notes")
    submitted  = st.form_submit_button("Create Task")

if submitted:
    new = api_post("/task", {
        "title": task_title or "Untitled Task",
        "description": task_notes,
        "project": proj_id,
    })
    st.success(f"Task created: ID {new['data']['id']}")
    st.balloons()
