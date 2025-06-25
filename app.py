import streamlit as st
import requests
import json

# -------------------- Config --------------------
API_BASE = "https://api.basicops.com/v2"
TOKEN = st.secrets.get("basicops_pat")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

st.set_page_config(page_title="BasicOps Forms", layout="centered")
st.title("📝 BasicOps Task Form (PAT Mode)")

if not TOKEN:
    st.error("No token found. Please set `basicops_pat` in your Streamlit secrets.")
    st.stop()

# -------------------- API Helpers --------------------
def api_get(path):
    res = requests.get(f"{API_BASE}{path}", headers=HEADERS)
    if not res.ok:
        st.error(f"GET {path} failed: {res.status_code}")
        st.stop()
    return res.json()

def api_post(path, payload):
    res = requests.post(f"{API_BASE}{path}", headers=HEADERS, data=json.dumps(payload))
    if not res.ok:
        st.error(f"POST {path} failed: {res.status_code}\n{res.text}")
        st.stop()
    return res.json()

# -------------------- Project Picker --------------------
projects_data = api_get("/projects?limit=100")
project_options = {p["name"]: p["id"] for p in projects_data.get("items", [])}
project_name = st.selectbox("Select a Project", list(project_options.keys()))
project_id = project_options[project_name]

project = api_get(f"/projects/{project_id}")
fields = project.get("fields", [])

# -------------------- Form --------------------
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
