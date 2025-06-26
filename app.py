import streamlit as st
import requests, time, json, datetime

"""
BasicOps Forms – **FULL DEBUG VERSION** (fixed response shapes)
--------------------------------------------------------------
• Handles {success,data:[...]} envelope on list endpoints
• Handles {success,data:{...fields:[...]}} on project‑detail
• Keeps verbose logging for every request/response
"""

# ── CONFIG ───────────────────────────────────────────────
API_BASE     = "https://api.basicops.com/v1"
AUTH_URL     = "https://app.basicops.com/oauth/auth"
TOKEN_URL    = "https://api.basicops.com/oauth/token"
CLIENT_ID    = st.secrets["basicops_client_id"]
CLIENT_SEC   = st.secrets["basicops_client_secret"]
REDIRECT_URI = st.secrets["basicops_redirect_uri"]

st.set_page_config("BasicOps Forms – DEBUG", layout="centered")
st.title("📝 BasicOps Task Form (OAuth) — DEBUG")

# ── TOKEN HELPERS ───────────────────────────────────────

def save_tokens(tok: dict):
    st.session_state.update({
        "access_token":  tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "expires_at":    time.time() + tok.get("expires_in", 3600) - 60,
    })

def token_valid():
    return "access_token" in st.session_state and time.time() < st.session_state.get("expires_at", 0)

def refresh_token():
    if "refresh_token" not in st.session_state:
        return False
    st.write("↻ Refreshing token …")
    r = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SEC,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "refresh_token",
        "refresh_token": st.session_state["refresh_token"],
    }, timeout=10)
    st.write("Refresh status", r.status_code)
    st.write(r.text[:300])
    if r.ok and r.json().get("access_token"):
        save_tokens(r.json())
        return True
    return False

def ensure_token():
    if not token_valid() and not refresh_token():
        st.warning("Token missing or expired — click Connect")
        st.stop()

# ── API WRAPPERS WITH DEBUG ────────────────────────────

def api_get(path: str):
    ensure_token()
    url = f"{API_BASE}{path}"
    st.write("GET", url)
    r = requests.get(url, headers={"Authorization": f"Bearer {st.session_state['access_token']}"}, timeout=10)
    st.write("Status", r.status_code)
    st.write(r.text[:300])
    if not r.ok:
        st.error(f"GET failed → {r.status_code}")
        st.stop()
    try:
        return r.json()
    except Exception:
        st.error("Response was not JSON (snippet above)")
        st.stop()


def api_post(path: str, payload: dict):
    ensure_token()
    url = f"{API_BASE}{path}"
    st.write("POST", url)
    st.write("Payload", payload)
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {st.session_state['access_token']}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=10,
    )
    st.write("Status", r.status_code)
    st.write(r.text[:300])
    if not r.ok:
        st.error("POST failed — see above")
        st.stop()
    return r.json()

# ── OAUTH CODE FLOW ────────────────────────────────────
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
    st.write("Token exchange status", r.status_code)
    st.write(r.text[:300])
    if r.ok and r.json().get("access_token"):
        save_tokens(r.json())
        st.query_params.clear()
        st.rerun()
    else:
        st.error("Token exchange failed — details above")
        st.stop()

# ── LOGIN BUTTON ───────────────────────────────────────
if not token_valid():
    auth = f"{AUTH_URL}?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}"
    st.markdown(f"[🔑 Connect to BasicOps]({auth})", unsafe_allow_html=True)
    st.stop()

st.success("Connected — token valid ✅")

# ── PROJECT LIST (enveloped) ───────────────────────────
proj_resp = api_get("/project?limit=100")
proj_data = proj_resp.get("data", []) if isinstance(proj_resp, dict) else proj_resp

st.write("🔍 Raw project response", proj_resp)

if not isinstance(proj_data, list) or not proj_data:
    st.error("Project list empty or unexpected shape.")
    st.stop()

proj_map = {p.get("title", f"Unnamed {i}"): p["id"] for i, p in enumerate(proj_data)}
sel_name = st.selectbox("Select a Project", list(proj_map.keys()))
proj_id = proj_map[sel_name]

# ── PROJECT DETAIL & FIELDS (enveloped) ───────────────
proj_detail_resp = api_get(f"/project/{proj_id}")
p_detail = proj_detail_resp.get("data", {}) if isinstance(proj_detail_resp, dict) else proj_detail_resp
fields = p_detail.get("fields", [])

st.write("🧩 Full project detail", p_detail)
st.write("🔍 Fields for project", fields)

if not fields:
    st.warning("No custom fields found; only base title/desc will be used.")

# ── DYNAMIC FORM ───────────────────────────────────────
with st.form("task_form"):
    base_title = st.text_input("Task title")
    base_desc = st.text_area("Description")

    field_values = {}
    for f in fields:
        fid, flabel, ftype = f["id"], f.get("label", fid), f.get("type", "text")
        if ftype in ("singleline", "text"):
            field_values[fid] = st.text_input(flabel, key=fid)
        elif ftype == "multiline":
            field_values[fid] = st.text_area(flabel, key=fid)
        elif ftype == "select":
            opts = {o["label"]: o["value"] for o in f.get("options", [])}
            choice = st.selectbox(flabel, list(opts.keys()) or ["-- none --"], key=fid)
            field_values[fid] = opts.get(choice)
        elif ftype == "checkbox":
            field_values[fid] = st.checkbox(flabel, key=fid)
        elif ftype == "date":
            dt = st.date_input(flabel, key=fid)
            field_values[fid] = dt.isoformat() if isinstance(dt, datetime.date) else ""
        elif ftype == "number":
            field_values[fid] = st.number_input(flabel, key=fid)
        else:
            st.warning(f"Unknown field type '{ftype}' — using text input")
            field_values[fid] = st.text_input(flabel, key=fid)

    submitted = st.form_submit_button("Create Task")

if submitted:
    payload = {
        "title": base_title or "Untitled Task",
        "description": base_desc,
        "project": proj_id,
        "fields": field_values,
    }
    st.write("Submitting payload", payload)
    new_task = api_post("/task", payload)
    st.success(f"✅ Task created: {new_task.get('data', {}).get('id', 'unknown')}")
    st.balloons()
