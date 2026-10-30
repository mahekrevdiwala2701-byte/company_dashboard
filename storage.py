"""Saving pivot layouts (rows, values, calculated fields, sorting, filters).

Where they are kept
  • In your browser (default, no setup): the browser's own storage. Survives page reloads, app
    restarts and redeploys. It belongs to that browser on that computer.
  • Google Sheets (optional, shared by everyone/every device): add a service account to Streamlit
    secrets → layouts go to a tab called "dashboard_layouts".
Your unsaved changes (the draft) are always kept in the browser too, so a reload never loses work.
"""

import json
from pathlib import Path

import streamlit as st

from data import MAPPING_SHEET_ID

TAB = "dashboard_layouts"
LOCAL_FILE = Path(__file__).with_name("saved_layouts.json")       # last resort: browser storage blocked
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BROWSER_KEY = "sector_rotation_pivot_v1"
ss = st.session_state


# ---------------------------------------------------------------- where
def backend() -> str:
    try:
        if "gcp_service_account" in st.secrets:
            return "sheets"
    except Exception:                       # no secrets.toml at all
        pass
    return "browser" if not ss.get("_br_blocked") else "file"


def where() -> str:
    return {"sheets": "your Google Sheet (tab “dashboard_layouts”)",
            "browser": "this browser — kept after reloads and app restarts",
            "file": "the server (your browser blocks storage) — lost when the app restarts"}[backend()]


# ---------------------------------------------------------------- browser storage bridge
_JS = """
export default function(component) {
  const { data, setStateValue } = component;
  const KEY = "%s";
  try {
    if (data && data.nonce && window.__srNonce !== data.nonce) {      // Python asked us to write
      window.__srNonce = data.nonce;
      if (data.write != null) localStorage.setItem(KEY, data.write);
    }
    if (!window.__srLoaded) {                                          // first run in this tab: read
      window.__srLoaded = true;
      setStateValue("stored", localStorage.getItem(KEY) || "");
    }
  } catch (e) {
    if (!window.__srLoaded) { window.__srLoaded = true; setStateValue("stored", "__blocked__"); }
  }
}
""" % BROWSER_KEY
_bridge = st.components.v2.component("sr_storage_bridge", js=_JS)


def _on_stored() -> None:
    state = ss.get("srbridge")
    raw = state.get("stored") if isinstance(state, dict) else getattr(state, "stored", None)
    if raw is None:
        return
    if raw == "__blocked__":
        ss._br_blocked, data = True, {}
    else:
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
    ss._br_data = data
    ss._br_last = raw if raw not in ("", "__blocked__") else None
    ss._br_fresh = True                     # the dashboard applies it once


def browser_loaded() -> bool:
    return "_br_data" in ss


def take_fresh() -> dict | None:
    """The browser's saved data, once, right after it arrives (None otherwise)."""
    if ss.get("_br_fresh"):
        ss._br_fresh = False
        return ss.get("_br_data") or {}
    return None


def sync(payload: dict) -> None:
    """Call at the END of every run: mounts the (invisible) bridge and writes `payload` to the
    browser when it changed. Nothing is written until the browser's data has been read."""
    if browser_loaded() and not ss.get("_br_blocked"):
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if text != ss.get("_br_last"):
            ss._br_last = text
            ss._br_nonce = ss.get("_br_nonce", 0) + 1
    with st.container(key="srbridge_box"):
        _bridge(key="srbridge", data={"write": ss.get("_br_last"), "nonce": ss.get("_br_nonce", 0)},
                default={"stored": None}, on_stored_change=_on_stored, height=0)


# ---------------------------------------------------------------- Google Sheets
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


# ---------------------------------------------------------------- load / save
def load_all() -> dict[str, dict]:
    """{layout name: layout}."""
    try:
        if backend() == "sheets":
            rows = _worksheet().get_all_values()
            return {r[0]: json.loads(r[1]) for r in rows if len(r) >= 2 and r[0] and r[1]}
        if backend() == "browser":
            return dict((ss.get("_br_data") or {}).get("layouts") or {})
        if LOCAL_FILE.exists():
            return json.loads(LOCAL_FILE.read_text("utf-8"))
    except Exception as e:
        st.toast(f"Couldn't read saved layouts: {e}", icon="⚠️")
    return {}


def save_all(layouts: dict[str, dict]) -> bool:
    """Sheets/file are written now; the browser copy is written by sync() at the end of this run."""
    try:
        if backend() == "sheets":
            ws = _worksheet()
            rows = [[name, json.dumps(lay, ensure_ascii=False)] for name, lay in layouts.items()]
            ws.clear()
            if rows:
                ws.update(range_name="A1", values=rows)
        elif backend() == "file":
            LOCAL_FILE.write_text(json.dumps(layouts, ensure_ascii=False, indent=2), "utf-8")
        return True
    except Exception as e:
        st.error(f"Couldn't save: {e}")
        return False