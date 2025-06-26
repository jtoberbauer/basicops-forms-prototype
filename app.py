import time
import json
from urllib.parse import urlencode

import requests
import streamlit as st

"""
BasicOps Forms → Task Prototype (OAuth) — **FIXED**
--------------------------------------------------
This version eliminates all previously‑seen crashes:
• guards against missing `access_token` / `expires_at`
• uses only modern `st.query_params` & `st.rerun()`
• shows raw API errors to speed debugging

Secrets required in `.streamlit/secrets.toml` (and in Streamlit Cloud > Secrets):

```
basicops_client_id = "YOUR_CLIENT_ID"
basicops_client_secret = "YOUR_CLIENT_SECRET"
redirect_uri = "https://<your‑streamlit‑slug>.streamlit.app"
```
"""
# ───────────────────────── CONFIG ──────────────────────────
API_BASE    = "https://api.basicops.com/v2"          # REST base
AUTH_URL    = "https://app.basicops.com/oauth/auth"  # OAuth authorize
TOKEN_URL   = "https://api.basicops.com/oauth/token" # OAuth token
CLIENT_ID   = st.secrets["basicops_client_id"]
CLIENT_SEC  = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["redirect_uri"]
SCOPE       = "read write"

st.set_page_config(page_title="BasicOps Forms", layout="centered")
st.title("📝 BasicOps Task Form (OAuth)")

# ───────────────────── SESSION HELPERS ─────────────────────

def save_tokens(tok_json: dict):
    """Persist access / refresh tokens & expiry in session state."""
    st.session_state["access_token"]  = tok_json["access_token"]
    st.session_state["refresh_token"] = tok_json.get("refresh_token")
    st.session_state["expires_at"]    = time.time() + tok_json.get("expires_in", 3600) - 60  # 1‑min slack


def token_valid() -> bool:
    """True if we have a non‑expired access token."""
    return (
        "access_token" in st.session_state and
        time.time() < st.session_state.get("expires_at", 0)
    )


def refresh_token() -> bool:
    """Attempt silent refresh with stored refresh_token."""
    if "refresh_token" not in st.session_state:
        return False
    res = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SEC,
            "refresh_token": st.session_state["refresh_token"],
        }, timeout=10,
    )
    if res.ok:
        save_tokens(res.json())
        return True
    return False

# ─────────────────────── API WRAPPERS ──────────────────────

def require_token():
    if not token_valid() and not refresh_token():
        st.error("Session expired. Please reconnect.")
        st.stop()


def api_get(path: str):
    require_token()
    if "access_token" not in st.session_state:
        st.error("No access token. Click ‘Connect to BasicOps’.")
        st.stop()
    res = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {st.session_state['access_token']}"},
        timeout=10,
    )
    if not res.ok:
        st.error(f"API GET {path} → {res.status_code}: {res.text}")
        st.stop()
    try:
        return res.json()
    except Exception as e:
        st.error(f"Failed JSON parse: {e}")
        st.write(res.text)
        st.stop()


def api_post(path: str, payload: dict):
    require_token()
    res = requests.post(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {st.session_state['access_token']}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=10,
    )
    if not res.ok:
        st.error(f"API POST {path} → {res.status_code}: {res.text}")
        st.stop()
    return res.json()

# ───────────── HANDLE OAUTH REDIRECT (?code=…) ─────────────
if "code" in st.query_params and "access_token" not in st.session_state:
    code = st.query_params["code"]
    res = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SEC,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "code": code,
        }, timeout=10,
    )
    if res.ok:
        tok = res.json()
        if not tok.get("access_token"):
            st.error(f"Token response missing access_token → {tok}")
            st.stop()
        save_tokens(tok)
        st.query_params.clear()  # drop ?code
        st.rerun()
    else:
        st.error(f"OAuth token exchange failed: {res.status_code} {res.text}")
        st.stop()

# ─────────────── AUTH UI (login button) ────────────────────
if not token_valid():
    params = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    })
    login_url = f"{AUTH_URL}?{params}"
    st.markdown(f"[🔑 Connect to BasicOps]({login_url})", unsafe_allow_html=True)
    st.stop()

st.success("Connected to BasicOps ✅")

# ─────────────────── MAIN APP (project → task) ─────────────
projects = api_get("/projects?limit=100").get("items", [])
proj_map = {p["name"]: p["id"] for p in projects}
if not proj_map:
    st.error("No projects returned. Check API permissions / scopes.")
    st.stop()

sel_name = st.selectbox("Select a Project", list(proj_map.keys()))
proj_id  = proj_map[sel_name]
proj_data = api_get(f"/projects/{proj_id}")
fields = proj_data.get("fields", [])

st.subheader("Create Task in ‘" + sel_name + "’")
with st.form("task_form"):
    task_name = st.text_input("Task name", max_chars=120)
    field_vals = {}
    for f in fields:
        label, fid, ftype = f["label"], f["id"], f["type"]
        if ftype == "multiline":
            field_vals[fid] = st.text_area(label)
        elif ftype == "select":
            opts = {o["label"]: o["value"] for o in f.get("options", [])}
            choice = st.selectbox(label, list(opts.keys())) if opts else ""
            field_vals[fid] = opts.get(choice, "")
        elif ftype == "date":
            dt = st.date_input(label)
            field_vals[fid] = dt.isoformat() if dt else ""
        elif ftype == "checkbox":
            field_vals[fid] = st.checkbox(label)
        elif ftype == "number":
            field_vals[fid] = st.number_input(label)
        else:
            field_vals[fid] = st.text_input(label)

    submitted = st.form_submit_button("Create Task")

if submitted:
    payload = {
        "project_id": proj_id,
        "name": task_name or "Untitled Task",
        "fields": field_vals,
    }
    new_task = api_post("/tasks", payload)
    st.success(f"✅ Created task #{new_task['id']} in {sel_name}")
    st.balloons()
