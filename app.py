"""
BasicOps Forms → Task Prototype (OAuth Version)
------------------------------------------------
Streamlit app that lets a user:
1. Connect to BasicOps via OAuth 2.0
2. Choose a project
3. Fill out a form auto‑generated from custom project fields
4. Submit → creates a new Task via BasicOps API

Add these to `.streamlit/secrets.toml` **(never commit)**:

```
basicops_client_id = "YOUR_CLIENT_ID"
basicops_client_secret = "YOUR_CLIENT_SECRET"
redirect_uri = "https://basicops-forms-prototype.streamlit.app"
```
"""
import time
import json
import requests
import streamlit as st
from urllib.parse import urlencode

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_BASE   = "https://api.basicops.com/v2"
AUTH_URL   = "https://app.basicops.com/oauth/auth"
TOKEN_URL  = "https://api.basicops.com/oauth/token"
CLIENT_ID  = st.secrets["basicops_client_id"]
CLIENT_SEC = st.secrets["basicops_client_secret"]
REDIRECT   = st.secrets["redirect_uri"]
SCOPE      = "read write"

st.set_page_config(page_title="BasicOps Forms", layout="centered")
st.title("📝 BasicOps Task Form (OAuth)")

# Handle OAuth redirect back with ?code=...
if "code" in st.query_params:
    code = st.query_params["code"]
    st.write("OAuth code received:", code)  # 👈 Debug line

    # Exchange code for access token
    token_response = requests.post(
        "https://api.basicops.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "code": code,
        },
    )

    st.write("Token response:", token_response.status_code, token_response.text)  # 👈 Debug line

    if token_response.status_code == 200:
        token_data = token_response.json()
        st.session_state["access_token"] = token_data["access_token"]
        st.experimental_rerun()
    else:
        st.error("Failed to authenticate with BasicOps.")


# ── SESSION HELPERS ──────────────────────────────────────────────────────────

def save_tokens(tok_json: dict):
    st.session_state["access_token"]  = tok_json["access_token"]
    st.session_state["refresh_token"] = tok_json.get("refresh_token")
    st.session_state["expires_at"]    = time.time() + tok_json.get("expires_in", 3600) - 60


def token_valid() -> bool:
    return "access_token" in st.session_state and time.time() < st.session_state["expires_at"]


def refresh_token() -> bool:
    if "refresh_token" not in st.session_state:
        return False
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SEC,
            "refresh_token": st.session_state["refresh_token"],
        },
        timeout=15,
    )
    if resp.ok:
        save_tokens(resp.json())
        return True
    return False


def api_get(path: str):
    if not token_valid() and not refresh_token():
        st.warning("Session expired, please reconnect.")
        st.stop()
    res = requests.get(f"{API_BASE}{path}", headers={"Authorization": f"Bearer {st.session_state['access_token']}"})
    if not res.ok:
        st.error(f"API error {res.status_code}")
        st.stop()
    return res.json()


def api_post(path: str, payload: dict):
    res = requests.post(
        f"{API_BASE}{path}",
        headers={
            "Authorization": f"Bearer {st.session_state['access_token']}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
    )
    if not res.ok:
        st.error(f"API POST failed {res.status_code}: {res.text}")
        st.stop()
    return res.json()

# ── HANDLE OAUTH REDIRECT ────────────────────────────────────────────────────
code_param = st.query_params.get("code")
if code_param and not token_valid():
    # If query param is list, take first elem
    if isinstance(code_param, list):
        code_param = code_param[0]
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SEC,
            "redirect_uri": REDIRECT,
            "code": code_param,
        },
        timeout=15,
    )
    if token_resp.ok:
        save_tokens(token_resp.json())
        # Clean URL (remove ?code)
        st.markdown('<meta http-equiv="refresh" content="0;url=/" />', unsafe_allow_html=True)
        st.stop()
    else:
        st.error("OAuth token exchange failed.")

# ── AUTH UI ──────────────────────────────────────────────────────────────────
if not token_valid():
    params = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT,
        "scope": SCOPE,
    })
    login_url = f"{AUTH_URL}?{params}"
    st.markdown(f"[🔑 Connect to BasicOps]({login_url})", unsafe_allow_html=True)
    st.stop()

# ── MAIN APP ─────────────────────────────────────────────────────────────────
projects = api_get("/projects?limit=100").get("items", [])
proj_map = {p["name"]: p["id"] for p in projects}

sel_name = st.selectbox("Select a Project", list(proj_map.keys()))
proj_id  = proj_map[sel_name]
proj     = api_get(f"/projects/{proj_id}")
fields   = proj.get("fields", [])

st.subheader("Create a Task")
with st.form("task_form"):
    task_name = st.text_input("Task Name", max_chars=120)
    field_vals = {}

    for f in fields:
        label, f_id, f_type = f["label"], f["id"], f["type"]
        if f_type == "multiline":
            field_vals[f_id] = st.text_area(label)
        elif f_type == "select":
            opts = {o["label"]: o["value"] for o in f.get("options", [])}
            choice = st.selectbox(label, list(opts.keys())) if opts else ""
            field_vals[f_id] = opts.get(choice, "")
        elif f_type == "date":
            dt = st.date_input(label)
            field_vals[f_id] = dt.isoformat() if dt else ""
        elif f_type == "checkbox":
            field_vals[f_id] = st.checkbox(label)
        elif f_type == "number":
            field_vals[f_id] = st.number_input(label)
        else:
            field_vals[f_id] = st.text_input(label)

    submitted = st.form_submit_button("Create Task")

if submitted:
    payload = {
        "project_id": proj_id,
        "name": task_name or "Untitled Task",
        "fields": field_vals,
    }
    new_task = api_post("/tasks", payload)
    st.success(f"✅ Created task #{new_task['id']}")
    st.balloons()
