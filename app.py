import streamlit as st
import requests
import time

# ── SECRETS ────────────────────────────────────────────────────────────────────
CLIENT_ID = st.secrets["basicops_client_id"]
CLIENT_SECRET = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["basicops_redirect_uri"]
BASE_URL = "https://api.basicops.com/v1"

# ── FUNCTIONS ──────────────────────────────────────────────────────────────────

def exchange_code_for_token(code):
    token_resp = requests.post(
        "https://api.basicops.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=15,
    )

    if token_resp.status_code == 200:
        tok_data = token_resp.json()
        st.session_state["access_token"] = tok_data["access_token"]
        st.session_state["refresh_token"] = tok_data["refresh_token"]
        st.session_state["expires_at"] = time.time() + tok_data.get("expires_in", 3600)
        st.experimental_rerun()
    else:
        st.error("Failed to exchange token.")
        st.stop()

def token_valid():
    return (
        "access_token" in st.session_state
        and time.time() < st.session_state["expires_at"]
    )

def api_get(path):
    res = requests.get(
        BASE_URL + path,
        headers={"Authorization": f"Bearer {st.session_state['access_token']}"},
        timeout=15,
    )
    if not res.ok:
        st.error(f"API error {res.status_code}")
        st.stop()
    return res.json()

def api_post(path, payload):
    res = requests.post(
        BASE_URL + path,
        headers={
            "Authorization": f"Bearer {st.session_state['access_token']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    if not res.ok:
        st.error(f"Post failed {res.status_code}: {res.text}")
        st.stop()
    return res.json()

# ── MAIN ───────────────────────────────────────────────────────────────────────

st.title("📝 BasicOps Task Form (OAuth)")

query_params = st.query_params
if "code" in query_params and not token_valid():
    code = query_params["code"]
    st.write(f"OAuth code received: {code}")
    exchange_code_for_token(code)

if not token_valid():
    auth_url = (
        "https://app.basicops.com/oauth/auth?"
        f"client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}"
    )
    st.markdown(f"🔑 [Connect to BasicOps]({auth_url})")
    st.stop()

projects = api_get("/projects?limit=100").get("items", [])
proj_map = {p["name"]: p["id"] for p in projects}

sel_name = st.selectbox("Select a Project", list(proj_map.keys()))
task_title = st.text_input("Task Title")
task_notes = st.text_area("Task Notes")

if st.button("Create Task"):
    payload = {
        "title": task_title,
        "notes": task_notes,
        "project_id": proj_map[sel_name],
    }
    res = api_post("/task", payload)
    st.success(f"Task created! ID: {res['id']}")