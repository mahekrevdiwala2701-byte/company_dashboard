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
INK, MUTED, LINE, ACCENT = "#0F172A", "#64748B", "#E5E7EB", "#047857"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root { color-scheme: light only; }
html, body, .stApp, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
.stApp { background: #F7F7F4 !important; color: #0F172A !important; }
.block-container { padding-top: 4.2rem; padding-bottom: 3rem; max-width: 1480px; }
header[data-testid="stHeader"] { background: #FFFFFF !important; border-bottom: 1px solid #E5E7EB; }
section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"] { display: none; }

/* top navigation links */
header[data-testid="stHeader"] a { font-weight: 600; color: #475569 !important; }
header[data-testid="stHeader"] a[aria-current="page"],
header[data-testid="stHeader"] a[aria-selected="true"] { color: #047857 !important; }

/* page title */
.title-row { display: flex; align-items: flex-end; justify-content: space-between;
             gap: 16px; flex-wrap: wrap; margin: 2px 0 18px; }
.eyebrow { font-size: .72rem; font-weight: 700; letter-spacing: .14em; color: #047857;
           text-transform: uppercase; }
.title-row h1 { font-size: 1.9rem; font-weight: 800; color: #0F172A; margin: 2px 0 0;
                padding: 0; letter-spacing: -.02em; }
.title-row .desc { color: #64748B; font-size: .9rem; margin-top: 4px; }
.live { display: inline-flex; align-items: center; gap: 8px; font-size: .8rem; color: #334155;
        background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 999px; padding: 6px 12px; }
.live i { width: 8px; height: 8px; border-radius: 50%; background: #10B981;
          box-shadow: 0 0 0 3px rgba(16,185,129,.18); }

/* filter bar */
.st-key-filterbar { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 14px;
                    padding: 14px 16px 16px; }
.stApp [data-testid="stWidgetLabel"] p { color: #475569; font-size: .78rem; font-weight: 600;
                                         text-transform: uppercase; letter-spacing: .06em; }
.stApp div[data-baseweb="select"] > div,
.stApp div[data-baseweb="input"] { background: #FFFFFF; border: 1px solid #E2E8F0 !important;
                                  border-radius: 10px !important; min-height: 40px; }
.stApp div[data-baseweb="input"] input { background: #FFFFFF; font-size: .9rem; }
.stApp div[data-baseweb="input"]:focus-within,
.stApp div[data-baseweb="select"] > div:focus-within { border-color: #047857 !important;
                                                       box-shadow: 0 0 0 3px rgba(4,120,87,.12); }
.stApp div[data-baseweb="input"] [data-testid="stTextInputIcon"] { color: #94A3B8; }
.stApp span[data-baseweb="tag"] { background: #ECFDF5 !important; border-radius: 6px !important; }
.stApp span[data-baseweb="tag"] span { color: #065F46 !important; }

/* buttons */
.stButton button { height: 40px; border-radius: 10px; font-weight: 600; font-size: .85rem;
                   padding: 0 10px; transition: all .15s ease; box-shadow: none; }
.stButton button p, .stButton button div { white-space: nowrap; overflow: visible; text-overflow: clip; }
.stButton button[kind="secondary"] { background: #FFFFFF; color: #334155; border: 1px solid #E2E8F0; }
.stButton button[kind="secondary"]:hover { background: #F8FAFC; color: #0F172A; border-color: #CBD5E1; }
.stButton button[kind="primary"] { background: #047857; color: #FFFFFF; border: 1px solid #047857; }
.stButton button[kind="primary"]:hover { background: #065F46; border-color: #065F46; }
.stButton button:disabled, .stButton button:disabled:hover { background: #F1F5F9 !important;
    color: #94A3B8 !important; border-color: #E2E8F0 !important; }
.stButton button:active { transform: translateY(1px); }
.stButton button:focus:not(:active) { box-shadow: 0 0 0 3px rgba(4,120,87,.15); }

/* stat strip: one panel split into cells */
.strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); background: #FFFFFF;
         border: 1px solid #E5E7EB; border-radius: 14px; margin: 14px 0 22px; overflow: hidden; }
.strip .cell { padding: 16px 20px; border-left: 1px solid #F1F5F9; }
.strip .cell:first-child { border-left: none; background: #0F172A; }
.strip .cell:first-child .k, .strip .cell:first-child .s { color: #94A3B8; }
.strip .cell:first-child .v { color: #FFFFFF; }
.strip .k { font-size: .72rem; font-weight: 700; color: #64748B; letter-spacing: .1em;
            text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.strip .v { font-size: 1.75rem; font-weight: 800; color: #0F172A; margin-top: 6px;
            font-variant-numeric: tabular-nums; letter-spacing: -.02em; line-height: 1.1; }
.strip .s { font-size: .78rem; color: #94A3B8; margin-top: 2px; }
@media (max-width: 900px) { .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                            .strip .cell { border-top: 1px solid #F1F5F9; } }

/* section heading */
.sec { display: flex; align-items: baseline; gap: 10px; margin: 6px 0 8px; }
.sec b { font-size: 1.05rem; color: #0F172A; }
.sec span { color: #64748B; font-size: .85rem; }

/* layout bar */
.st-key-pvbar { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 14px;
                padding: 12px 16px 14px; margin-bottom: 16px; }
.pv-status { height: 40px; display: flex; align-items: center; margin-bottom: 1rem; font-size: .82rem; font-weight: 600; }
.pv-status.ok { color: #047857; } .pv-status.warn { color: #B45309; }
.st-key-pvbar [data-testid="stToggle"] { height: 40px; display: flex; align-items: center; }

/* pivot editor panel */
.st-key-pveditor { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 14px; padding: 16px; }
.pe-title { font-size: 1rem; font-weight: 800; color: #0F172A; margin-bottom: 6px; }
.pe-h { font-size: .8rem; font-weight: 800; color: #0F172A; text-transform: uppercase; letter-spacing: .08em;
        margin: 6px 0 4px; }
.pe-sub { font-size: .75rem; color: #64748B; margin: 6px 0 2px; }
.pe-lvl { font-size: .82rem; font-weight: 600; color: #334155; white-space: nowrap; overflow: hidden;
          text-overflow: ellipsis; }
.pe-name { font-weight: 700; font-size: .86rem; color: #0F172A; white-space: nowrap; overflow: hidden;
           text-overflow: ellipsis; }
.pe-fx { display: inline-block; font: 700 10px/1 'Plus Jakarta Sans'; color: #047857; background: #ECFDF5;
         border-radius: 5px; padding: 3px 5px; margin-right: 6px; vertical-align: 1px; }
.pe-formula { font: 500 12px/1.4 ui-monospace, Menlo, monospace; color: #334155; background: #F8FAFC;
              border: 1px solid #EEF2F6; border-radius: 8px; padding: 6px 8px; margin: 2px 0 6px;
              white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
[class*="st-key-pvcard_"] { background: #FCFCFD; border-radius: 12px !important; }
[class*="st-key-pvcard_"] .stButton button[kind="tertiary"] { height: 28px; min-height: 28px; padding: 0 4px;
                                                               color: #64748B; border: none; }
[class*="st-key-pvcard_"] .stButton button[kind="tertiary"]:hover { color: #047857; background: #ECFDF5; }
.f-err { color: #B91C1C; background: #FEF2F2; border: 1px solid #FECACA; border-radius: 10px;
         padding: 8px 12px; font-size: .85rem; }
.f-ok { color: #065F46; background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px;
        padding: 8px 12px; font-size: .85rem; }
div[data-testid="stDialog"] div[role="dialog"] { border-radius: 16px; }

div[data-testid="stDataFrame"] { background: #FFFFFF; border: 1px solid #E5E7EB;
                                 border-radius: 14px; padding: 4px; }
.stDownloadButton button { height: 40px; background: #047857; color: #FFFFFF; border: 1px solid #047857;
                           border-radius: 10px; font-weight: 600; padding: 0 16px; }
.stDownloadButton button:hover { background: #065F46; color: #FFFFFF; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_title(eyebrow: str, title: str, desc: str) -> None:
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b, %I:%M %p")
    st.markdown(
        f'<div class="title-row"><div><div class="eyebrow">{eyebrow}</div><h1>{title}</h1>'
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
    items = [("Companies", len(view), len(df))] + [
        (lbl, _n(view, c), _n(df, c)) for lbl, c in
        [("Sectors", "Sector"), ("Industries", "Industry"),
         ("Industry groups", "Industry Group"), ("Sub groups", "Industry Sub group")]
    ]
    cells = "".join(
        f'<div class="cell"><div class="k">{k}</div><div class="v">{v:,}</div>'
        f'<div class="s">{"all" if v == t else f"of {t:,}"}</div></div>'
        for k, v, t in items
    )
    st.markdown(f'<div class="strip">{cells}</div>', unsafe_allow_html=True)


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
.card{{background:#fff;border:1px solid {LINE};border-radius:14px;overflow:hidden}}
/* toolbar */
.bar{{display:flex;gap:10px;align-items:center;padding:12px;border-bottom:1px solid {LINE};flex-wrap:wrap}}
.seg{{display:inline-flex;background:#F1F5F9;border-radius:10px;padding:3px;gap:2px}}
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
thead th{{position:sticky;top:0;z-index:2;height:42px;background:#F8FAFC;color:#64748B;font-size:11px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;text-align:left;border-bottom:1px solid {LINE};cursor:pointer;user-select:none}}
thead th:hover{{color:{INK}}}
thead th em{{font-style:normal;color:{ACCENT};margin-left:4px}}
th.num,td.num{{text-align:right;font-variant-numeric:tabular-nums;min-width:118px}}
td.name,th.name{{position:sticky;left:0;z-index:1;background:inherit;width:360px;min-width:360px;max-width:360px;
  border-right:1px solid {LINE}}}
thead th.name{{z-index:3;background:#F8FAFC}}
.nm{{display:flex;align-items:center;gap:8px;min-width:0}}
.nm .t{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
tr{{background:#fff}} tr.g{{cursor:pointer}}
tr.d0{{background:#F8FAFC;font-weight:700}} tr.d0 td{{border-bottom-color:#E2E8F0}}
tr.d1{{font-weight:600}} tr.d2{{font-weight:600;color:#334155}}
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
tfoot td{{position:sticky;bottom:0;height:44px;background:{INK};color:#fff;font-weight:700;border:none;z-index:2}}
tfoot td.name{{z-index:3;background:{INK};border-right-color:#1E293B}}
tfoot .cnt{{background:rgba(255,255,255,.14);color:#E2E8F0}}
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
const MAX_ROWS=600; let budget=0, cut=0;   // never draw more than this many rows at once
// give every node a stable id
(function tag(rows,p,d){{rows.forEach((r,i)=>{{r.id=p+"/"+i;r.d=d;if(r.kids)tag(r.kids,r.id,d+1);}});}})(T.rows,"",0);
const F=T.formats||[];
const fmt=(v,i)=>v==null?"–":v.toLocaleString("en-IN",{{minimumFractionDigits:2,maximumFractionDigits:2}})+(F[i]==="percent"?"%":"");
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
  let h=`<tr class="${{g?"g d"+r.d:"leaf"}}${{isOpen?" open":""}}" data-id="${{r.id}}"><td class="name" title="${{esc(r.label)}}"><div class="nm" style="padding-left:${{pad}}px">${{name}}</div></td>`;
  r.vals.forEach((v,i)=>h+=`<td class="num" style="${{bg(v,L[r.d][i])}}">${{fmt(v,i)}}</td>`);
  h+="</tr>"; if(isOpen) h+=sorted(r.kids.filter(keep)).map(rowHtml).join(""); return h; }}
function render(){{
  budget=MAX_ROWS; cut=0;
  const rows=sorted(T.rows.filter(keep));
  let out=rows.length?rows.map(rowHtml).join("")
    :`<tr><td class="empty" colspan="${{M.length+1}}">Nothing matches “${{esc(q)}}”</td></tr>`;
  if(cut) out+=`<tr><td class="empty" colspan="${{M.length+1}}">Showing the first 600 rows — type more of the name, or use the filters above, to see the rest.</td></tr>`;
  document.getElementById("tb").innerHTML=out;
  document.querySelectorAll("thead th").forEach(th=>{{const i=+th.dataset.i;
    th.querySelector("em").textContent=(i===sortI&&sortDir)?(sortDir>0?"▲":"▼"):"";}});
}}
(function foot(){{ const tr=document.querySelector("tfoot tr");
  document.getElementById("gt").textContent=T.total.n.toLocaleString("en-IN");
  T.total.vals.forEach((v,i)=>tr.insertAdjacentHTML("beforeend",`<td class="num">${{fmt(v,i)}}</td>`)); }})();
document.getElementById("tb").addEventListener("click",e=>{{const tr=e.target.closest("tr.g"); if(!tr) return;
  const id=tr.dataset.id; open.has(id)?open.delete(id):open.add(id); render();}});
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