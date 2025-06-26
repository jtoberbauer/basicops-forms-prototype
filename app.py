import streamlit as st
import requests, time, json

"""
BasicOps Forms – **DEBUG BUILD**
--------------------------------
Adds verbose prints so we can see:
1. Token exchange status + body
2. Exact URL & auth header on each request
3. Raw (first 400 chars) of every API response before JSON parse
Remove debug lines once everything works.
"""

# ── CONFIG ───────────────────────────────────────────────
API_BASE     = "https://api.basicops.com/v1"
AUTH_URL     = "https://app.basicops.com/oauth/auth"
TOKEN_URL    = "https://api.basicops.com/oauth/token"
CLIENT_ID    = st.secrets["basicops_client_id"]
CLIENT_SEC   = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["basicops_redirect_uri"]

# ── PAGE SETUP ───────────────────────────────────────────
st.set_page_config("BasicOps Forms – DEBUG", layout="centered")
st.title("📝 BasicOps Task Form (OAuth) – DEBUG")

# ── SESSION HELPERS ─────────────────────────────────────

def save_tokens(tok: dict):
    st.session_state["access_token"]  = tok["access_token"]
    st.session_state["refresh_token"] = tok.get("refresh_token")
    st.session_state["expires_at"]    = time.time() + tok.get("expires_in", 3600) - 60


def token_valid() -> bool:
    return (
        "access_token" in st.session_state and
        time.time() < st.session_state.get("expires_at", 0)
    )


def refresh_token() -> bool:
    if "refresh_token" not in st.session_state:
        return False
    st.write("↻ Refreshing token…")
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SEC,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "refresh_token",
        "refresh_token": st.session_state["refresh_token"],
    }, timeout=10)
    st.write("Refresh status", r.status_code)
    st.write(r.text[:400])
    if r.ok and r.json().get("access_token"):
        save_tokens(r.json())
        return True
    return False

# ── API WRAPPERS (with debug) ───────────────────────────

def ensure_token():
    if not token_valid() and not refresh_token():
        st.warning("Session expired. Reconnect.")
        st.stop()


def api_get(path: str):
    ensure_token()
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
    st.write("GET", url)
    st.write("Auth", headers)
    r = requests.get(url, headers=headers, timeout=10)
    st.write("Status", r.status_code)
    st.write(r.text[:400])
    if not r.ok:
        st.error(f"API {r.status_code}")
        st.stop()
    try:
        return r.json()
    except Exception:
        st.error("Response not JSON (see above snippet)")
        st.stop()


def api_post(path: str, payload: dict):
    ensure_token()
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {st.session_state['access_token']}",
        "Content-Type": "application/json",
    }
    st.write("POST", url)
    st.write("Payload", payload)
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
    st.write("Status", r.status_code)
    st.write(r.text[:400])
    if not r.ok:
        st.error("Post failed")
        st.stop()
    return r.json()

# ── HANDLE ?code= ───────────────────────────────────────
if "code" in st.query_params and "access_token" not in st.session_state:
    code = st.query_params["code"]
    st.write("OAuth code received", code)
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SEC,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code": code,
    }, timeout=10)
    st.write("Token status", r.status_code)
    st.write("Token body", r.text[:400])
    if r.ok and r.json().get("access_token"):
        save_tokens(r.json())
        st.query_params.clear()
        st.rerun()
    else:
        st.error("Token exchange failed; see details above")
        st.stop()

# ── LOGIN BUTTON ────────────────────────────────────────
if not token_valid():
    params = f"client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}"
    st.markdown(f"[🔑 Connect to BasicOps]({AUTH_URL}?{params})", unsafe_allow_html=True)
    st.stop()

st.success("Connected ✅ – token valid")

# ── PROJECT PICKER (debug prints will show) ─────────────
proj_resp = api_get("/project?limit=100")
projects  = proj_resp.get("data", [])
if not projects:
    st.error("No projects returned.")
    st.stop()

proj_map = {p["title"]: p["id"] for p in projects}
sel_name = st.selectbox("Select Project", list(proj_map.keys()))
proj_id  = proj_map[sel_name]

with st.form("task_form"):
    ttitle = st.text_input("Task title")
    tdesc  = st.text_area("Description")
    ok = st.form_submit_button("Create Task")

if ok:
    new = api_post("/task", {
        "title": ttitle or "Untitled Task",
        "description": tdesc,
        "project": proj_id,
    })
    st.success(f"Task #{new['data']['id']} created")
