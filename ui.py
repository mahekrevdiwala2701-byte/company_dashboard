"""Look & feel and reusable pieces: styling, header, filter bar, stat strip, tables."""

import html as _html
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from data import LEVELS

FILTER_KEYS = [f"f_{level}" for level in LEVELS] + ["f_company"]
UNMAPPED = "Unmapped"
TREE_COLS = ["Name", "NSE Code", "BSE Code"] + LEVELS     # text columns the expandable table needs

# palette: ink + emerald on warm white (deliberately unlike the purple dashboards)
INK, MUTED, LINE, ACCENT = "#0F172A", "#64748B", "#E2E8F0", "#0F766E"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

/* palette: deep teal + cyan, warm amber accent (different from the purple dashboards) */
:root { color-scheme: light only;
  --teal-900:#134E4A; --teal-800:#115E59; --teal-700:#0F766E; --teal-600:#0D9488; --teal-500:#14B8A6;
  --teal-50:#F0FDFA; --teal-100:#CCFBF1; --cyan-700:#0E7490; --amber:#F59E0B; --amber-50:#FFFBEB;
  --ink:#0F172A; --muted:#64748B; --line:#E2E8F0; }
html, body, .stApp, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, #DDF4F1 0%, transparent 60%),
                     linear-gradient(180deg, #F0F7F6 0%, #F8FAFC 420px) !important; color: var(--ink) !important; }
.block-container { padding-top: 4.4rem; padding-bottom: 3rem; max-width: 1560px; }
header[data-testid="stHeader"] { background: rgba(255,255,255,.92) !important; backdrop-filter: blur(8px);
                                 border-bottom: 1px solid var(--line); }
section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"] { display: none; }

/* top navigation */
header[data-testid="stHeader"] a { font-weight: 700; color: #475569 !important; border-radius: 10px; }
header[data-testid="stHeader"] a[aria-current="page"],
header[data-testid="stHeader"] a[aria-selected="true"] { color: var(--teal-700) !important; background: var(--teal-50) !important; }

/* hero banner */
.hero { position: relative; overflow: hidden; border-radius: 20px; padding: 24px 28px; margin: 2px 0 18px;
        color: #fff; background: linear-gradient(115deg, var(--teal-900) 0%, var(--teal-700) 45%, var(--cyan-700) 100%);
        box-shadow: 0 14px 34px -14px rgba(15,118,110,.55); display: flex; justify-content: space-between;
        align-items: flex-end; gap: 16px; flex-wrap: wrap; }
.hero::before { content: ""; position: absolute; right: -60px; top: -80px; width: 320px; height: 320px; border-radius: 50%;
                background: radial-gradient(circle, rgba(255,255,255,.18), transparent 65%); }
.hero::after { content: ""; position: absolute; left: 35%; bottom: -120px; width: 360px; height: 240px; border-radius: 50%;
               background: radial-gradient(circle, rgba(245,158,11,.28), transparent 65%); }
.hero > * { position: relative; z-index: 1; }
.hero .eyebrow { font-size: .72rem; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; color: #FDE68A; }
.hero h1 { font-size: 2rem; font-weight: 800; color: #fff !important; margin: 4px 0 0; padding: 0; letter-spacing: -.02em; }
.hero .desc { color: #CCFBF1; font-size: .92rem; margin-top: 4px; }
.live { display: inline-flex; align-items: center; gap: 8px; font-size: .8rem; font-weight: 600; color: #fff;
        background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); border-radius: 999px; padding: 7px 14px; }
.live i { width: 8px; height: 8px; border-radius: 50%; background: #4ADE80; box-shadow: 0 0 0 4px rgba(74,222,128,.25); }

/* cards */
.st-key-filterbar, .st-key-pvbar, .st-key-colbar {
  background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px 16px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px -12px rgba(15,23,42,.18); }
.st-key-filterbar { border-top: 4px solid var(--teal-600); }
.st-key-pvbar { margin-bottom: 14px; border-left: 4px solid var(--amber); }
.st-key-colbar { margin-bottom: 10px; padding: 10px 14px 12px; }
.st-key-colbar [data-testid="stWidgetLabel"] { display: none; }

/* inputs */
.stApp [data-testid="stWidgetLabel"] p { color: var(--teal-800); font-size: .74rem; font-weight: 800;
                                         text-transform: uppercase; letter-spacing: .08em; }
.stApp div[data-baseweb="select"] > div,
.stApp div[data-baseweb="input"] { background: #F8FAFC; border: 1px solid var(--line) !important;
                                  border-radius: 10px !important; min-height: 40px; }
.stApp div[data-baseweb="input"] input { background: transparent; font-size: .9rem; }
.stApp div[data-baseweb="input"]:focus-within,
.stApp div[data-baseweb="select"] > div:focus-within { border-color: var(--teal-600) !important; background: #fff;
                                                       box-shadow: 0 0 0 3px rgba(13,148,136,.15); }
.stApp span[data-baseweb="tag"] { background: var(--teal-700) !important; border-radius: 7px !important; }
.stApp span[data-baseweb="tag"] span { color: #fff !important; }
.stApp span[data-baseweb="tag"] svg { fill: #fff !important; }

/* buttons */
.stButton button, .stDownloadButton button, [data-testid="stPopover"] button {
  height: 40px; border-radius: 10px; font-weight: 700; font-size: .85rem; padding: 0 12px; transition: all .15s ease; }
.stButton button p, .stButton button div { white-space: nowrap; overflow: visible; text-overflow: clip; }
.stButton button[kind="secondary"], [data-testid="stPopover"] button {
  background: #fff; color: var(--teal-800); border: 1px solid #B6E3DD; }
.stButton button[kind="secondary"]:hover, [data-testid="stPopover"] button:hover {
  background: var(--teal-50); color: var(--teal-900); border-color: var(--teal-500); }
.stButton button[kind="primary"], .stDownloadButton button {
  background: linear-gradient(135deg, var(--teal-600), var(--teal-800)); color: #fff; border: none;
  box-shadow: 0 6px 14px -8px rgba(15,118,110,.8); }
.stButton button[kind="primary"]:hover, .stDownloadButton button:hover { filter: brightness(1.08); color: #fff; }
.stButton button[kind="tertiary"] { color: var(--muted); }
.stButton button[kind="tertiary"]:hover { color: var(--teal-700); background: var(--teal-50); }
.stButton button:disabled, .stButton button:disabled:hover, [data-testid="stPopover"] button:disabled {
  background: #F1F5F9 !important; color: #94A3B8 !important; border-color: var(--line) !important;
  box-shadow: none !important; filter: none; }
.stButton button:active { transform: translateY(1px); }

/* stat tiles */
.tiles { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 14px; margin: 16px 0 18px; }
.tile { --c: var(--teal-600); --bg: var(--teal-50); position: relative; overflow: hidden; background: #fff;
        border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px; display: flex; gap: 12px; align-items: center;
        box-shadow: 0 6px 18px -14px rgba(15,23,42,.35); }
.tile::after { content: ""; position: absolute; inset: auto 0 0 0; height: 4px; background: var(--c); }
.tile .ic { flex: none; width: 42px; height: 42px; border-radius: 12px; background: var(--bg); color: var(--c);
            display: flex; align-items: center; justify-content: center; font-size: 1.25rem; }
.tile .k { font-size: .7rem; font-weight: 800; color: var(--muted); letter-spacing: .1em; text-transform: uppercase;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .v { font-size: 1.6rem; font-weight: 800; color: var(--ink); line-height: 1.1; font-variant-numeric: tabular-nums; }
.tile .s { font-size: .74rem; color: var(--c); font-weight: 700; }
.tile.t1 { --c:#0F766E; --bg:#CCFBF1; } .tile.t2 { --c:#0284C7; --bg:#E0F2FE; } .tile.t3 { --c:#D97706; --bg:#FEF3C7; }
.tile.t4 { --c:#E11D48; --bg:#FFE4E6; } .tile.t5 { --c:#65A30D; --bg:#ECFCCB; }
@media (max-width: 1000px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

/* section heading */
.sec { display: flex; align-items: center; gap: 10px; margin: 8px 0 10px; flex-wrap: wrap; }
.sec b { font-size: 1.05rem; color: var(--ink); padding-left: 10px; border-left: 4px solid var(--amber); line-height: 1.2; }
.sec span { color: var(--muted); font-size: .84rem; }

/* layout bar */
.pv-status { height: 40px; display: flex; align-items: center; margin-bottom: 1rem; font-size: .82rem; font-weight: 700; }
.pv-status.ok { color: var(--teal-700); } .pv-status.warn { color: #B45309; }

/* pivot editor side panel */
[data-testid="stColumn"]:has(> div > div > .st-key-pveditor) > div,
[data-testid="stColumn"]:has(.st-key-pveditor) > [data-testid="stVerticalBlock"] { height: 100%; }
.st-key-pveditor { position: sticky; top: 6.9rem; max-height: calc(100vh - 7.6rem); overflow-y: auto;
                   background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 0 16px 16px;
                   box-shadow: 0 18px 40px -22px rgba(15,23,42,.45); scrollbar-width: thin; }
[data-testid="stLayoutWrapper"]:has(> .st-key-pehead) { position: sticky; top: 0; z-index: 5;
    margin: 0 -16px 6px; width: calc(100% + 32px) !important; max-width: none !important; }
.st-key-pehead { width: 100% !important;
                 padding: 10px 12px 10px 16px;
                 background: linear-gradient(115deg, var(--teal-800), var(--cyan-700)); border-radius: 18px 18px 0 0; }
.st-key-pehead .pe-title { color: #fff; font-size: 1rem; font-weight: 800; display: flex; align-items: center; gap: 8px; }
.st-key-pehead .pe-title small { font-weight: 600; color: #A7F3D0; font-size: .75rem; }
.st-key-pehead .stButton { display: flex; justify-content: flex-end; }
.st-key-pehead .stButton button { background: rgba(255,255,255,.15) !important; color: #fff !important; width: 36px !important;
                                  min-width: 36px; height: 36px; padding: 0; border: 1px solid rgba(255,255,255,.3) !important; }
.st-key-pehead .stButton button:hover { background: rgba(255,255,255,.28) !important; }
.pe-h { display: flex; align-items: center; gap: 8px; font-size: .78rem; font-weight: 800; color: var(--teal-900);
        text-transform: uppercase; letter-spacing: .1em; margin: 14px 0 6px; padding: 6px 10px;
        background: var(--teal-50); border-radius: 8px; border-left: 3px solid var(--teal-600); }
.pe-sub { font-size: .75rem; color: var(--muted); margin: 6px 0 2px; }
.pe-lvl { font-size: .82rem; font-weight: 700; color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.f-err { color: #B91C1C; background: #FEF2F2; border: 1px solid #FECACA; border-radius: 10px; padding: 8px 12px; font-size: .85rem; }
.f-ok { color: #065F46; background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px; padding: 8px 12px; font-size: .85rem; }
div[data-testid="stDialog"] div[role="dialog"] { border-radius: 18px; border-top: 5px solid var(--teal-600); }
.stApp [data-testid="stExpander"] details { border-radius: 12px; border-color: #B6E3DD; background: var(--teal-50); }

/* "open editor" tab on the right edge when the panel is closed */
.st-key-pvopen, [data-testid="stLayoutWrapper"]:has(> .st-key-pvopen) {
    position: fixed !important; right: 0; top: 46%; z-index: 999; width: auto !important; pointer-events: none; }
.st-key-pvopen .stButton, .st-key-pvopen button { pointer-events: auto; }
.st-key-pvopen .stButton button { height: auto; padding: 14px 10px; writing-mode: vertical-rl; border-radius: 12px 0 0 12px;
  background: linear-gradient(180deg, var(--teal-600), var(--cyan-700)); color: #fff; border: none;
  box-shadow: -6px 6px 18px -8px rgba(15,118,110,.7); letter-spacing: .04em; }
.st-key-pvopen .stButton button:hover { filter: brightness(1.1); color: #fff; }

div[data-testid="stDataFrame"] { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 4px; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_title(eyebrow: str, title: str, desc: str) -> None:
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b, %I:%M %p")
    st.markdown(
        f'<div class="hero"><div><div class="eyebrow">{eyebrow}</div><h1>{title}</h1>'
        f'<div class="desc">{desc}</div></div>'
        f'<div class="live"><i></i>Live from Google Sheets · {now}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="sec"><b>{title}</b><span>{sub}</span></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- filter bar (linked)
def _clear():
    for k in FILTER_KEYS:
        st.session_state[k] = "" if k == "f_company" else []


def _refresh():
    st.cache_data.clear()
    st.session_state.pop("pv_layouts", None)          # re-read saved pivot layouts too


def _keep_valid(state_key: str, options) -> None:
    if state_key in st.session_state:
        valid = set(options)
        st.session_state[state_key] = [v for v in st.session_state[state_key] if v in valid]


def filter_bar(df: pd.DataFrame) -> pd.DataFrame:
    """Sector › Industry › Group › Sub group (each list limited by the ones before it) + company search."""
    view = df
    with st.container(key="filterbar"):
        cols = st.columns([1, 1, 1, 1, 1.25, 1.35], vertical_alignment="bottom")
        for col, level in zip(cols, LEVELS):
            options = sorted(v for v in view[level].unique() if v != "")
            k = f"f_{level}"
            _keep_valid(k, options)
            chosen = col.multiselect(level, options, key=k, placeholder=f"All ({len(options)})")
            if chosen:
                view = view[view[level].isin(chosen)]

        q = cols[4].text_input("Company", key="f_company", placeholder="Name, NSE or BSE code",
                               icon=":material/search:").strip()
        if q:
            view = view[view["_search"].str.contains(q.lower(), regex=False)]

        with cols[5].container(key="actions"):
            b1, b2 = st.columns(2, gap="small")
            b1.button("Reset", on_click=_clear, icon=":material/restart_alt:", key="btn_reset",
                      help="Clear every filter", width="stretch")
            b2.button("Refresh", on_click=_refresh, icon=":material/sync:", key="btn_refresh",
                      type="primary", help="Reload data from Google Sheets", width="stretch")
    return view


# ---------------------------------------------------------------- stat strip
def _n(frame: pd.DataFrame, col: str) -> int:
    return frame[col].replace("", pd.NA).nunique()


def stat_strip(view: pd.DataFrame, df: pd.DataFrame) -> None:
    items = [("🏢", "Companies", len(view), len(df))] + [
        (icon, lbl, _n(view, c), _n(df, c)) for icon, lbl, c in
        [("🧭", "Sectors", "Sector"), ("🏭", "Industries", "Industry"),
         ("🗂️", "Industry groups", "Industry Group"), ("🧩", "Sub groups", "Industry Sub group")]
    ]
    tiles = "".join(
        f'<div class="tile t{i}"><div class="ic">{icon}</div><div><div class="k">{k}</div>'
        f'<div class="v">{v:,}</div><div class="s">{"all in view" if v == t else f"of {t:,} total"}</div></div></div>'
        for i, (icon, k, v, t) in enumerate(items, 1)
    )
    st.markdown(f'<div class="tiles">{tiles}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- colour-coded dataframe
def color_limit(s: pd.Series, skip_never_negative: bool = True) -> float:
    """Colour scale limit: 95th percentile of |value|, so one outlier doesn't wash out the rest.
    Returns 0 (= don't colour) for columns that are never negative, e.g. price or market cap."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty or (skip_never_negative and (s >= 0).all()):
        return 0.0
    lim = float(s.abs().quantile(0.95))
    return lim if lim > 0 else 1.0


def cell_bg(v, lim: float) -> str:
    """Soft green for positive, soft red for negative; stronger the bigger the value."""
    if lim <= 0 or v is None or pd.isna(v):
        return ""
    a = 0.06 + 0.52 * min(1.0, abs(v) / lim)
    rgb = "22,163,74" if v >= 0 else "220,38,38"
    return f"background-color: rgba({rgb},{a:.3f})"


def styled(frame: pd.DataFrame, cols: list[str]):
    sty = frame.style.format({c: "{:,.2f}" for c in cols}, na_rep="–")
    for c in cols:
        lim = color_limit(frame[c])
        if lim:
            sty = sty.map(lambda v, lim=lim: cell_bg(v, lim), subset=[c])
    return sty.set_properties(**{"color": INK})


# ---------------------------------------------------------------- expandable pivot (rows built in pivot.py)
def _limits(tree: dict) -> list[list[float]]:
    """Per depth, per metric colour limit (companies are compared with companies, sectors with sectors)."""
    depth_vals: dict[int, list] = {}

    def walk(rows, d):
        for r in rows:
            depth_vals.setdefault(d, []).append(r["vals"])
            if "kids" in r:
                walk(r["kids"], d + 1)

    walk(tree["rows"], 0)
    n = len(tree["metrics"])
    frames = [pd.DataFrame(depth_vals.get(d, []), columns=range(n), dtype=float)
              for d in range(len(tree["levels"]) + 1)]
    companies = frames[-1]
    coloured = [color_limit(companies[i]) > 0 for i in range(n)]          # e.g. price → plain
    return [[color_limit(f[i], skip_never_negative=False) if ok else 0.0
             for i, ok in enumerate(coloured)] for f in frames]


def pivot_html(tree: dict, height: int) -> str:
    tree["limits"] = _limits(tree)
    payload = json.dumps(tree, ensure_ascii=False).replace("</", "<\\/")
    heads = "".join(f'<th class="num" data-i="{i}">{_html.escape(m)}<em></em></th>'
                    for i, m in enumerate(tree["metrics"]))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}} html,body{{margin:0;background:transparent;color-scheme:light only}}
body{{font-family:'Plus Jakarta Sans',sans-serif;color:{INK};font-size:13px}}
.card{{background:#fff;border:1px solid {LINE};border-radius:16px;overflow:hidden;box-shadow:0 10px 28px -18px rgba(15,23,42,.45)}}
/* toolbar */
.bar{{display:flex;gap:10px;align-items:center;padding:12px;border-bottom:1px solid {LINE};flex-wrap:wrap;background:linear-gradient(180deg,#F0FDFA,#fff)}}
.seg{{display:inline-flex;background:#CCFBF1;border-radius:10px;padding:3px;gap:2px}}
.seg button{{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border:none;border-radius:8px;
  background:transparent;color:#334155;font:600 12.5px 'Plus Jakarta Sans',sans-serif;cursor:pointer;transition:all .15s}}
.seg button:hover{{background:#fff;color:{ACCENT};box-shadow:0 1px 2px rgba(15,23,42,.08)}}
.seg svg{{width:14px;height:14px}}
.find{{position:relative;flex:1;min-width:220px;max-width:420px}}
.find svg{{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:15px;height:15px;color:#94A3B8}}
.find input{{width:100%;height:36px;padding:0 12px 0 34px;border:1px solid #E2E8F0;border-radius:10px;
  font:500 13px 'Plus Jakarta Sans',sans-serif;color:{INK};outline:none;background:#fff;transition:all .15s}}
.find input:focus{{border-color:{ACCENT};box-shadow:0 0 0 3px rgba(4,120,87,.12)}}
.hint{{color:#94A3B8;font-size:12px;margin-left:auto}}
/* table */
.wrap{{overflow:auto;max-height:{height}px}}
table{{border-collapse:separate;border-spacing:0;width:100%;min-width:max-content}}
th,td{{height:40px;padding:0 14px;border-bottom:1px solid #F1F5F9;white-space:nowrap;vertical-align:middle}}
thead th{{position:sticky;top:0;z-index:2;height:46px;background:#134E4A;color:#CCFBF1;font-size:11px;font-weight:800;
  letter-spacing:.06em;text-transform:uppercase;text-align:left;border-bottom:3px solid #F59E0B;cursor:pointer;user-select:none;white-space:normal;line-height:1.25;min-width:118px}}
thead th:hover{{color:#fff;background:#115E59}}
thead th em{{font-style:normal;color:#FCD34D;margin-left:4px}}
th.num,td.num{{text-align:right;font-variant-numeric:tabular-nums;min-width:118px}}
td.name,th.name{{position:sticky;left:0;z-index:1;background:inherit;width:360px;min-width:360px;max-width:360px;
  border-right:1px solid {LINE}}}
thead th.name{{z-index:3;background:#134E4A}}
.nm{{display:flex;align-items:center;gap:8px;min-width:0}}
.nm .t{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
tr{{background:#fff}} tr.g{{cursor:pointer}}
tr.d0{{background:#F0FDFA;font-weight:800}} tr.d0 td{{border-bottom-color:#CCFBF1}} tr.d0 td.name{{box-shadow:inset 4px 0 0 var(--sc,#0D9488)}}
tr.d1{{font-weight:700;background:#FFFFFF}} tr.d1 td.name{{box-shadow:inset 4px 0 0 #99F6E4}} tr.d2{{font-weight:600;color:#334155}}
tr.leaf td{{height:36px;color:#334155}}
tr:hover td{{background-image:linear-gradient(rgba(15,23,42,.04),rgba(15,23,42,.04))}}
.tog{{flex:none;display:inline-flex;width:20px;height:20px;border-radius:6px;align-items:center;justify-content:center;
  background:#ECFDF5;color:{ACCENT};transition:transform .15s,background .15s}}
.tog svg{{width:12px;height:12px}}
tr.g:hover .tog{{background:{ACCENT};color:#fff}}
tr.open .tog{{transform:rotate(90deg);background:{ACCENT};color:#fff}}
.cnt{{flex:none;font-size:11px;font-weight:600;color:{MUTED};background:#F1F5F9;border-radius:999px;padding:2px 8px;line-height:1.3}}
.code{{flex:none;font-size:11px;font-weight:600;color:{ACCENT};background:#ECFDF5;border-radius:6px;padding:2px 6px;line-height:1.3}}
.dot{{flex:none;width:6px;height:6px;border-radius:50%;background:#CBD5E1;margin:0 7px}}
tfoot td{{position:sticky;bottom:0;height:46px;background:linear-gradient(90deg,#134E4A,#0E7490);background-attachment:fixed;color:#fff;font-weight:800;border:none;z-index:2;border-top:3px solid #F59E0B}}
tfoot td.name{{z-index:3;background:#134E4A;border-right-color:#115E59}}
tfoot .cnt{{background:rgba(255,255,255,.14);color:#E2E8F0}}
tr.more td{{height:38px;background:#FCFCFD;cursor:pointer}}
.morebtn{{color:{ACCENT};font-weight:700;font-size:12.5px}} .morebtn em{{font-style:normal;color:{MUTED};font-weight:500;margin-left:4px}}
tr.more:hover .morebtn{{text-decoration:underline}}
mark{{background:#FEF08A;color:inherit;border-radius:3px;padding:0 1px}}
.empty{{padding:40px;text-align:center;color:{MUTED}}}
</style></head><body>
<div class="card">
 <div class="bar">
  <div class="seg">
   <button id="co"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 20l5-5 5 5M7 4l5 5 5-5"/></svg>Collapse all</button>
  </div>
  <label class="find"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
   <input id="q" placeholder="Find a sector, group or company…"></label>
  <span class="hint">Click a row to open · click a heading to sort</span>
 </div>
 <div class="wrap"><table>
  <thead><tr><th class="name" data-i="-1">{_html.escape(" › ".join(tree["levels"] + ["Company"]))}<em></em></th>{heads}</tr></thead>
  <tbody id="tb"></tbody>
  <tfoot><tr><td class="name"><div class="nm"><span class="t">Grand Total</span><span class="cnt" id="gt"></span></div></td></tr></tfoot>
 </table></div>
</div>
<script>
const T={payload};
const M=T.metrics, L=T.limits, DEPTH=T.levels.length;
const open=new Set(); let sortI=null, sortDir=0, q="";
const MAX_ROWS=Math.max(150, Math.min(600, Math.floor(24000/Math.max(1,M.length)))); let budget=0, cut=0;   // cap cells drawn at once
// give every node a stable id
const byId={{}};
const PAL=["#0D9488","#0284C7","#D97706","#E11D48","#65A30D","#0891B2","#EA580C","#DB2777","#16A34A","#CA8A04","#2563EB","#9333EA"];
(function tag(rows,p,d){{rows.forEach((r,i)=>{{r.id=p+"/"+i;r.d=d;byId[r.id]=r;if(r.kids)tag(r.kids,r.id,d+1);}});}})(T.rows,"",0);
const F=T.formats||[], D=T.decimals||[];
const fmt=(v,i)=>{{ if(v==null) return "–"; const d=D[i]??2;
  return v.toLocaleString("en-IN",{{minimumFractionDigits:d,maximumFractionDigits:d}})+(F[i]==="percent"?"%":""); }};
function bg(v,lim){{ if(v==null||!lim) return "";
  const a=Math.min(1,Math.abs(v)/lim), al=(0.06+0.52*a).toFixed(3);
  return v>=0?`background-color:rgba(22,163,74,${{al}})`:`background-color:rgba(220,38,38,${{al}})`; }}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]));
function hl(s){{ s=esc(s); if(!q) return s; const i=s.toLowerCase().indexOf(q); return i<0?s:
  s.slice(0,i)+"<mark>"+s.slice(i,i+q.length)+"</mark>"+s.slice(i+q.length); }}
function hits(r){{ return (r.label+" "+(r.code||"")).toLowerCase().includes(q); }}
function keep(r){{ return !q || hits(r) || (r.kids||[]).some(keep); }}
function sorted(rows){{ if(sortI===null) return rows;
  return [...rows].sort((a,b)=>{{ let x,y; if(sortI<0){{x=a.label;y=b.label;return sortDir*x.localeCompare(y);}}
    x=a.vals[sortI];y=b.vals[sortI]; if(x==null) return 1; if(y==null) return -1; return sortDir*(x-y); }}); }}
function rowHtml(r){{
  if(budget<=0){{cut++;return "";}} budget--;
  const g=!!r.kids, isOpen=g&&(open.has(r.id)||(q&&!hits(r)&&r.kids.some(keep)));
  const pad=r.d*24;
  const tog=`<span class="tog"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></span>`;
  let name=g?`${{tog}}<span class="t">${{hl(r.label)}}</span><span class="cnt">${{r.n.toLocaleString("en-IN")}}</span>`
            :`<span class="dot"></span><span class="t">${{hl(r.label)}}</span>${{r.code?`<span class="code">${{esc(r.code)}}</span>`:""}}`;
  const sc=r.d===0?`style="--sc:${{PAL[(T.rows.indexOf(r)>=0?T.rows.indexOf(r):0)%PAL.length]}}"`:"";
  let h=`<tr class="${{g?"g d"+r.d:"leaf"}}${{isOpen?" open":""}}" data-id="${{r.id}}" ${{sc}}><td class="name" title="${{esc(r.label)}}"><div class="nm" style="padding-left:${{pad}}px">${{name}}</div></td>`;
  if(r.cells===undefined){{ let c=""; r.vals.forEach((v,i)=>c+=`<td class="num" style="${{bg(v,L[r.d][i])}}">${{fmt(v,i)}}</td>`); r.cells=c; }}
  h+=r.cells;                                   // cells are built once per row, then reused
  h+="</tr>"; if(isOpen) h+=sorted(r.kids.filter(keep)).map(rowHtml).join(""); return h; }}
function render(){{
  budget=MAX_ROWS; cut=0;
  const rows=sorted(T.rows.filter(keep));
  let out=rows.length?rows.map(rowHtml).join("")
    :`<tr><td class="empty" colspan="${{M.length+1}}">Nothing matches “${{esc(q)}}”</td></tr>`;
  if(cut) out+=`<tr><td class="empty" colspan="${{M.length+1}}">Showing the first ${{MAX_ROWS}} rows — type more of the name, or use the filters above, to see the rest.</td></tr>`;
  document.getElementById("tb").innerHTML=out;
  document.querySelectorAll("thead th").forEach(th=>{{const i=+th.dataset.i;
    th.querySelector("em").textContent=(i===sortI&&sortDir)?(sortDir>0?"▲":"▼"):"";}});
}}
(function foot(){{ const tr=document.querySelector("tfoot tr");
  if(!T.total){{ document.querySelector("tfoot").remove(); return; }}
  document.getElementById("gt").textContent=T.total.n.toLocaleString("en-IN");
  T.total.vals.forEach((v,i)=>tr.insertAdjacentHTML("beforeend",`<td class="num">${{fmt(v,i)}}</td>`)); }})();
document.getElementById("tb").addEventListener("click",e=>{{const tr=e.target.closest("tr.g"); if(!tr) return;
  const id=tr.dataset.id;
  if(q){{ open.has(id)?open.delete(id):open.add(id); render(); return; }}      // while searching: full redraw
  const node=byId[id];
  if(open.has(id)){{                                                         // close: remove only its rows
    open.delete(id); tr.classList.remove("open");
    let nx=tr.nextElementSibling;
    while(nx && nx.dataset.id && nx.dataset.id.startsWith(id+"/")){{ const d=nx; nx=nx.nextElementSibling; d.remove(); }}
    while(nx && !nx.dataset.id && nx.querySelector(".empty")){{ const d=nx; nx=nx.nextElementSibling; d.remove(); }}
  }} else {{                                                                  // open: add only its children
    open.add(id); tr.classList.add("open"); budget=MAX_ROWS; cut=0;
    const kids=sorted(node.kids.filter(keep));
    const leafy=kids.length && !kids[0].kids;                 // a group of companies
    const first=leafy ? kids.slice(0,PAGE) : kids;
    let h=first.map(rowHtml).join("");
    if(leafy && kids.length>PAGE) h+=moreRow(id, PAGE, kids.length);
    tr.insertAdjacentHTML("afterend",h);
  }}
}});
const PAGE=100;                                               // companies drawn per click
function moreRow(id, shown, total){{
  return `<tr class="more" data-id="${{id}}/more" data-of="${{id}}" data-shown="${{shown}}"><td class="name" colspan="1">`+
         `<div class="nm" style="padding-left:${{(id.split("/").length-1)*24}}px"><span class="morebtn">Show ${{Math.min(PAGE,total-shown)}} more `+
         `<em>(${{shown}} of ${{total.toLocaleString("en-IN")}})</em></span></div></td><td colspan="${{M.length}}"></td></tr>`; }}
document.getElementById("tb").addEventListener("click",e=>{{const tr=e.target.closest("tr.more"); if(!tr) return;
  const id=tr.dataset.of, shown=+tr.dataset.shown, kids=sorted(byId[id].kids.filter(keep));
  budget=MAX_ROWS; let h=kids.slice(shown, shown+PAGE).map(rowHtml).join("");
  if(kids.length>shown+PAGE) h+=moreRow(id, shown+PAGE, kids.length);
  tr.insertAdjacentHTML("afterend",h); tr.remove();
}});
document.querySelectorAll("thead th").forEach(th=>th.addEventListener("click",()=>{{const i=+th.dataset.i;
  const first=i<0?1:-1;               // names A→Z first, numbers high→low first
  if(sortI!==i){{sortI=i;sortDir=first;}} else if(sortDir===first) sortDir=-first; else {{sortI=null;sortDir=0;}}
  render();}}));
document.getElementById("co").onclick=()=>{{open.clear();render();}};
let timer; // wait until typing pauses; ignore 1-letter searches (they would open everything)
document.getElementById("q").addEventListener("input",e=>{{clearTimeout(timer);timer=setTimeout(()=>{{
  const v=e.target.value.trim().toLowerCase(); q=v.length>=2?v:""; render();}},250);}});
render();
</script></body></html>"""