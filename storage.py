"""Saving pivot layouts (rows, values, calculated fields, sorting).

Where they are saved
  • Google Sheets (recommended, survives restarts): add a service account to Streamlit secrets
    (see README section in the chat) — layouts go to a tab called "dashboard_layouts".
  • Otherwise: a file next to the app (saved_layouts.json). Works on your own computer, but
    Streamlit Cloud wipes it whenever the app restarts.
"""

import json
from pathlib import Path

import streamlit as st

from data import MAPPING_SHEET_ID

TAB = "dashboard_layouts"
LOCAL_FILE = Path(__file__).with_name("saved_layouts.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def backend() -> str:
    try:
        return "sheets" if "gcp_service_account" in st.secrets else "file"
    except Exception:                       # no secrets.toml at all
        return "file"


def where() -> str:
    return ("your Google Sheet (tab “dashboard_layouts”)" if backend() == "sheets"
            else "this server only — they’re lost when Streamlit Cloud restarts the app")


@st.cache_resource(show_spinner=False)
def _worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    sheet_id = st.secrets.get("layouts_sheet_id", MAPPING_SHEET_ID)
    sh = gspread.authorize(creds).open_by_key(sheet_id)
    try:
        return sh.worksheet(TAB)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(TAB, rows=50, cols=2)


def load_all() -> dict[str, dict]:
    """{layout name: layout}."""
    try:
        if backend() == "sheets":
            rows = _worksheet().get_all_values()
            return {r[0]: json.loads(r[1]) for r in rows if len(r) >= 2 and r[0] and r[1]}
        if LOCAL_FILE.exists():
            return json.loads(LOCAL_FILE.read_text("utf-8"))
    except Exception as e:
        st.toast(f"Couldn't read saved layouts: {e}", icon="⚠️")
    return {}


def save_all(layouts: dict[str, dict]) -> bool:
    try:
        if backend() == "sheets":
            ws = _worksheet()
            rows = [[name, json.dumps(lay, ensure_ascii=False)] for name, lay in layouts.items()]
            ws.clear()
            if rows:
                ws.update(range_name="A1", values=rows)
        else:
            LOCAL_FILE.write_text(json.dumps(layouts, ensure_ascii=False, indent=2), "utf-8")
        return True
    except Exception as e:
        st.error(f"Couldn't save: {e}")
        return False