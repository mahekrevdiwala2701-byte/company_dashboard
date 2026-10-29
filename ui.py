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
.st-key-filterbar { background: #FFFFFF; border: 1px solid #E5E7EB !important;
                    border-radius: 14px; padding: 4px 6px 2px; }
.stApp [data-testid="stWidgetLabel"] p { color: #475569; font-size: .78rem; font-weight: 600;
                                         text-transform: uppercase; letter-spacing: .06em; }
.stApp div[data-baseweb="select"] > div { background: #FFFFFF; border-color: #E2E8F0;
                                          border-radius: 10px; }
.stApp span[data-baseweb="tag"] { background: #ECFDF5 !important; }
.stApp span[data-baseweb="tag"] span { color: #065F46 !important; }
.stButton button { border-radius: 10px; font-weight: 600; border: 1px solid #E2E8F0;
                   background: #FFFFFF; color: #0F172A; }
.stButton button:hover { border-color: #047857; color: #047857; }

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

div[data-testid="stDataFrame"] { background: #FFFFFF; border: 1px solid #E5E7EB;
                                 border-radius: 14px; padding: 4px; }
.stDownloadButton button { background: #047857; color: #FFFFFF; border: none; border-radius: 10px;
                           font-weight: 600; }
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
        st.session_state[k] = []


def _refresh():
    st.cache_data.clear()


def _keep_valid(state_key: str, options) -> None:
    if state_key in st.session_state:
        valid = set(options)
        st.session_state[state_key] = [v for v in st.session_state[state_key] if v in valid]


def filter_bar(df: pd.DataFrame) -> pd.DataFrame:
    """Sector › Industry › Group › Sub group › Company, each list limited by the ones before it."""
    view = df
    with st.container(key="filterbar"):
        cols = st.columns([1, 1, 1, 1, 1.4, 0.55])
        for col, level in zip(cols, LEVELS):
            options = sorted(v for v in view[level].unique() if v != "")
            k = f"f_{level}"
            _keep_valid(k, options)
            chosen = col.multiselect(level, options, key=k, placeholder=f"All ({len(options)})")
            if chosen:
                view = view[view[level].isin(chosen)]

        search_cols = [c for c in ["Name", "NSE Code", "BSE Code"] if c in view.columns]
        labels = view[search_cols].astype(str).agg(lambda r: " · ".join(v for v in r if v), axis=1)
        options = sorted(labels.unique())
        _keep_valid("f_company", options)
        picked = cols[4].multiselect("Company", options, key="f_company",
                                     placeholder="Name, NSE or BSE code")
        if picked:
            view = view[labels.isin(picked)]

        with cols[5]:
            st.markdown('<div style="height:1.55rem"></div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            b1.button("✕", on_click=_clear, help="Clear all filters", width="stretch")
            b2.button("↻", on_click=_refresh, help="Reload data from Google Sheets", width="stretch")
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


# ---------------------------------------------------------------- expandable pivot (Sector › … › Company)
def build_tree(view: pd.DataFrame, levels: list[str], metrics: list[str], how: str) -> dict:
    """Nested {label, n, vals, kids} — group rows carry the average/median of their companies."""
    agg = "median" if how == "Median" else "mean"

    def vals(frame):
        out = frame[metrics].agg(agg) if len(frame) else pd.Series(index=metrics, dtype=float)
        return [None if pd.isna(v) else round(float(v), 4) for v in out]

    def node(frame, depth):
        if depth == len(levels):                                   # company rows
            code_col = "NSE Code" if "NSE Code" in frame.columns else None
            return [{"label": r.get("Name", "") or "—",
                     "code": (r.get(code_col) or r.get("BSE Code", "")) if code_col else r.get("BSE Code", ""),
                     "vals": [None if pd.isna(r[m]) else round(float(r[m]), 4) for m in metrics]}
                    for r in frame.to_dict("records")]
        level = levels[depth]
        g = frame[level].replace("", UNMAPPED)
        return [{"label": name, "n": len(part), "vals": vals(part), "kids": node(part, depth + 1)}
                for name, part in frame.groupby(g, sort=True)]

    return {"levels": levels, "metrics": metrics, "how": how,
            "rows": node(view, 0), "total": {"n": len(view), "vals": vals(view)}}


def _limits(tree: dict) -> list[list[float]]:
    """Per depth, per metric colour limit (companies are compared with companies, sectors with sectors)."""
    depth_vals: dict[int, list] = {}

    def walk(rows, d):
        for r in rows:
            depth_vals.setdefault(d, []).append(r["vals"])
            if "kids" in r:
                walk(r["kids"], d + 1)

    walk(tree["rows"], 0)
    frames = [pd.DataFrame(depth_vals.get(d, []), columns=tree["metrics"], dtype=float)
              for d in range(len(tree["levels"]) + 1)]
    companies = frames[-1]
    coloured = [color_limit(companies[m]) > 0 for m in tree["metrics"]]   # e.g. price → plain
    return [[color_limit(f[m], skip_never_negative=False) if ok else 0.0
             for m, ok in zip(tree["metrics"], coloured)] for f in frames]


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
.bar{{display:flex;gap:8px;align-items:center;padding:10px 12px;border-bottom:1px solid {LINE};flex-wrap:wrap}}
.bar button{{font:600 12px inherit;font-family:inherit;border:1px solid #E2E8F0;background:#fff;color:{INK};
  border-radius:8px;padding:6px 10px;cursor:pointer}}
.bar button:hover{{border-color:{ACCENT};color:{ACCENT}}}
.bar input{{flex:1;min-width:180px;font:inherit;border:1px solid #E2E8F0;border-radius:8px;padding:7px 10px;outline:none}}
.bar input:focus{{border-color:{ACCENT}}}
.bar .hint{{color:{MUTED};font-size:12px;margin-left:auto}}
.wrap{{overflow:auto;height:{height - 56}px}}
table{{border-collapse:separate;border-spacing:0;width:100%;min-width:max-content}}
th,td{{padding:7px 12px;border-bottom:1px solid #F1F5F9;white-space:nowrap}}
thead th{{position:sticky;top:0;z-index:2;background:#F8FAFC;color:#475569;font-size:11px;font-weight:700;
  letter-spacing:.06em;text-transform:uppercase;text-align:left;border-bottom:1px solid {LINE};cursor:pointer;user-select:none}}
thead th em{{font-style:normal;color:{ACCENT};margin-left:4px}}
th.num,td.num{{text-align:right;font-variant-numeric:tabular-nums}}
td.name,th.name{{position:sticky;left:0;z-index:1;background:inherit;min-width:340px;max-width:460px;
  overflow:hidden;text-overflow:ellipsis}}
thead th.name{{z-index:3;background:#F8FAFC}}
tr{{background:#fff}} tr.g{{cursor:pointer}}
tr.d0{{background:#F8FAFC;font-weight:700}} tr.d0 td{{border-bottom-color:#E2E8F0}}
tr.d1{{font-weight:600}} tr.d2{{font-weight:600;color:#334155}}
tr.leaf td.name{{color:#334155}}
tr:hover td{{background-image:linear-gradient(rgba(15,23,42,.035),rgba(15,23,42,.035))}}
.tog{{display:inline-flex;width:18px;height:18px;border-radius:5px;align-items:center;justify-content:center;
  background:{ACCENT};color:#fff;font-size:12px;margin-right:8px;vertical-align:-3px;transition:transform .15s}}
tr.open .tog{{transform:rotate(90deg)}}
.cnt{{display:inline-block;margin-left:8px;font-size:11px;font-weight:600;color:{MUTED};background:#F1F5F9;
  border-radius:999px;padding:1px 8px}}
.code{{display:inline-block;margin-left:8px;font-size:11px;color:{ACCENT};background:#ECFDF5;border-radius:6px;padding:1px 6px}}
.dot{{display:inline-block;width:6px;height:6px;border-radius:50%;background:#CBD5E1;margin:0 14px 0 6px;vertical-align:2px}}
tfoot td{{position:sticky;bottom:0;background:#0F172A;color:#fff;font-weight:700;border:none;z-index:2}}
tfoot td.name{{z-index:3;background:#0F172A}}
mark{{background:#FEF08A;color:inherit;border-radius:3px}}
.empty{{padding:40px;text-align:center;color:{MUTED}}}
</style></head><body>
<div class="card">
 <div class="bar">
  <button id="ex">⊞ Expand all</button><button id="co">⊟ Collapse all</button><button id="l1">Show next level</button>
  <input id="q" placeholder="Find a sector, group or company…">
  <span class="hint">Click a row to open it · click a column to sort · values = {tree["how"].lower()} of companies</span>
 </div>
 <div class="wrap"><table>
  <thead><tr><th class="name" data-i="-1">{_html.escape(" › ".join(tree["levels"] + ["Company"]))}<em></em></th>{heads}</tr></thead>
  <tbody id="tb"></tbody>
  <tfoot><tr><td class="name">Grand Total <span class="cnt" id="gt"></span></td></tr></tfoot>
 </table></div>
</div>
<script>
const T={payload};
const M=T.metrics, L=T.limits, DEPTH=T.levels.length;
const open=new Set(); let sortI=null, sortDir=0, q="";
// give every node a stable id
(function tag(rows,p,d){{rows.forEach((r,i)=>{{r.id=p+"/"+i;r.d=d;if(r.kids)tag(r.kids,r.id,d+1);}});}})(T.rows,"",0);
const fmt=v=>v==null?"–":v.toLocaleString("en-IN",{{minimumFractionDigits:2,maximumFractionDigits:2}});
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
  const g=!!r.kids, isOpen=g&&(open.has(r.id)||(q&&!hits(r)&&r.kids.some(keep)));
  const pad=14+r.d*22;
  let name=g?`<span class="tog">›</span>${{hl(r.label)}}<span class="cnt">${{r.n.toLocaleString("en-IN")}}</span>`
            :`<span class="dot"></span>${{hl(r.label)}}${{r.code?`<span class="code">${{esc(r.code)}}</span>`:""}}`;
  let h=`<tr class="${{g?"g d"+r.d:"leaf"}}${{isOpen?" open":""}}" data-id="${{r.id}}"><td class="name" style="padding-left:${{pad}}px" title="${{esc(r.label)}}">${{name}}</td>`;
  r.vals.forEach((v,i)=>h+=`<td class="num" style="${{bg(v,L[r.d][i])}}">${{fmt(v)}}</td>`);
  h+="</tr>"; if(isOpen) h+=sorted(r.kids.filter(keep)).map(rowHtml).join(""); return h; }}
function render(){{
  const rows=sorted(T.rows.filter(keep));
  document.getElementById("tb").innerHTML=rows.length?rows.map(rowHtml).join("")
    :`<tr><td class="empty" colspan="${{M.length+1}}">Nothing matches “${{esc(q)}}”</td></tr>`;
  document.querySelectorAll("thead th").forEach(th=>{{const i=+th.dataset.i;
    th.querySelector("em").textContent=(i===sortI&&sortDir)?(sortDir>0?"▲":"▼"):"";}});
}}
(function foot(){{ const tr=document.querySelector("tfoot tr");
  document.getElementById("gt").textContent=T.total.n.toLocaleString("en-IN");
  T.total.vals.forEach(v=>tr.insertAdjacentHTML("beforeend",`<td class="num">${{fmt(v)}}</td>`)); }})();
document.getElementById("tb").addEventListener("click",e=>{{const tr=e.target.closest("tr.g"); if(!tr) return;
  const id=tr.dataset.id; open.has(id)?open.delete(id):open.add(id); render();}});
document.querySelectorAll("thead th").forEach(th=>th.addEventListener("click",()=>{{const i=+th.dataset.i;
  const first=i<0?1:-1;               // names A→Z first, numbers high→low first
  if(sortI!==i){{sortI=i;sortDir=first;}} else if(sortDir===first) sortDir=-first; else {{sortI=null;sortDir=0;}}
  render();}}));
function all(rows,f){{rows.forEach(r=>{{if(r.kids){{f(r);all(r.kids,f);}}}});}}
document.getElementById("ex").onclick=()=>{{all(T.rows,r=>open.add(r.id));render();}};
document.getElementById("co").onclick=()=>{{open.clear();render();}};
document.getElementById("l1").onclick=()=>{{ // open one more level than is open now
  let d=0; while(true){{let any=false,full=true; all(T.rows,r=>{{if(r.d===d){{any=true;if(!open.has(r.id))full=false;}}}});
    if(!any) break; if(!full){{all(T.rows,r=>{{if(r.d===d)open.add(r.id);}});break;}} d++;}} render();}};
document.getElementById("q").addEventListener("input",e=>{{q=e.target.value.trim().toLowerCase();render();}});
render();
</script></body></html>"""