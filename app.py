"""
BasicOps Forms → Task Prototype (OAuth Version)
------------------------------------------------
Streamlit app that lets a user:
1. Connect to their BasicOps account via OAuth 2.0
2. Choose a project
3. Fill out a form auto‑generated from custom project fields
4. Submit → creates a new Task via BasicOps API

Secrets
=======
Add these to `.streamlit/secrets.toml` **(not committed)**:

```
basicops_client_id = "242f0e19-623d-451e-aa79-1930bc2e857a"
basicops_client_secret = "YOUR_CLIENT_SECRET"
redirect_uri = "https://<your‑app‑name>.streamlit.app"
```
"""
import time
import json
import requests
import streamlit as st
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs

# ---- CONFIG ----
API_BASE = "https://api.basicops.com/v2"
AUTH_URL = "https://basicops.com/oauth/auth"
TOKEN_URL = "https://basicops.com/oauth/token"
CLIENT_ID = st.secrets["basicops_client_id"]
CLIENT_SECRET = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["redirect_uri"]
SCOPE = "read write"

st.set_page_config(page_title="BasicOps Forms", layout="centered")
st.title("📝 BasicOps Task Form (OAuth)")

# ---- Session Helpers ----

def store_tokens(token_json: dict):
    """Save tokens & expiry in session_state"""
    st.session_state["access_token"] = token_json["access_token"]
    st.session_state["refresh_token"] = token_json.get("refresh_token")
    st.session_state["expires_at"] = time.time() + token_json.get("expires_in", 3600) - 60  # 60s buffer


def token_valid() -> bool:
    return "access_token" in st.session_state and time.time() < st.session_state["expires_at"]


def refresh_access_token() -> bool:
    """Try to refresh and store a new access token"""
    if "refresh_token" not in st.session_state:
        return False
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": st.session_state["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=15,
    )
    if resp.ok:
        store_tokens(resp.json())
        return True
    return False


def api_get(path: str):
    if not token_valid():
        if not refresh_access_token():
            st.warning("Session expired — please reconnect.")
            st.stop()
    headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
    res = requests.get(f"{API_BASE}{path}", headers=headers, timeout=20)
    if not res.ok:
        st.error(f"API error: {res.status_code}")
        st.stop()
    return res.json()


def api_post(path: str, payload: dict):
    headers = {
        "Authorization": f"Bearer {st.session_state['access_token']}",
        "Content-Type": "application/json",
    }
    res = requests.post(
        f"{API_BASE}{path}", headers=headers, data=json.dumps(payload), timeout=20
    )
    if not res.ok:
        st.error(f"API POST failed: {res.status_code} {res.text}")
        st.stop()
    return res.json()

# ---- OAuth Handshake ----
query_params = st.query_params
if "code" in query_params and not token_valid():
    code = query_params["code"][0]
    # Exchange code for tokens
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=15,
    )
    if token_resp.ok:
        store_tokens(token_resp.json())
        # Clean the URL (remove ?code=..)
        st.experimental_set_query_params()
    else:
        st.error("OAuth token exchange failed.")

# ---- UI Flow ----
if not token_valid():
    # Not connected — show login link
    auth_params = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
        }
    )
    st.markdown(
        f"[🔑 Connect to BasicOps]({AUTH_URL}?{auth_params})",
        unsafe_allow_html=True,
    )
    st.stop()

# ---- Step 1: Choose Project ----
projects_data = api_get("/projects?limit=100")
project_options = {proj["name"]: proj["id"] for proj in projects_data.get("items", [])}
project_name = st.selectbox("Select a Project", list(project_options.keys()))
project_id = project_options[project_name]

project = api_get(f"/projects/{project_id}")
fields = project.get("fields", [])

# ---- Step 2: Dynamic Form ----
st.subheader("Create a Task")
with st.form("task_form"):
    task_name = st.text_input("Task Name", max_chars=120)
    field_values = {}
    for f in fields:
        label = f["label"]
        f_id = f["id"]
        f_type = f["type"]
        if f_type == "multiline":
            field_values[f_id] = st.text_area(label)
        elif f_type == "select":
            opts = {o["label"]: o["value"] for o in f.get("options", [])}
            field_values[f_id] = opts[st.selectbox(label, list(opts.keys()))] if opts else ""
        elif f_type == "date":
            dt = st.date_input(label)
            field_values[f_id] = dt.isoformat() if dt else ""
        elif f_type == "checkbox":
            field_values[f_id] = st.checkbox(label)
        elif f_type == "number":
            field_values[f_id] = st.number_input(label)
        else:
            field_values[f_id] = st.text_input(label)

    submitted = st.form_submit_button("Create Task")

if submitted:
    payload = {
        "project_id": project_id,
        "name": task_name or "Untitled Task",
        "fields": field_values,
    }
    task = api_post("/tasks", payload)
    st.success(f"✅ Created task #{task['id']}")
    st.balloons()
