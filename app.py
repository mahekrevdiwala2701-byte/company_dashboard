"""
Streamlit app: Sector Rotation – Results Basis.

Data:
  • Results sheet   – one row per company (its "Industry" column = sub group)
  • Mapping sheet   – Sector › Industry › Industry Group › Industry Sub group
Both sheets must be shared as "Anyone with the link → Viewer".

Views (tabs):
  🏁 Leaderboard  – groups ranked by the chosen metric + breadth (% of companies positive)
  🔥 Heatmap      – groups × every numeric column, colour-coded medians
  🧭 Market map   – treemap Sector › Industry › Group › Sub group (size = companies, colour = metric)
  🚀 Movers       – top / bottom companies on the chosen metric + distribution
  📋 Companies    – full colour-coded table + CSV download

Run:  streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------- config
RESULTS_SHEET_ID = "1Q1Siumntv5nBbH8D282S7Bnltl7Ys_PaScFXD_Z__KE"
RESULTS_GID = "1378148789"
MAPPING_SHEET_ID = "1mDjmc-Nu9ulobXqo2A9GCHP9_OcmMd9GJnm5swf9QEM"
MAPPING_GID = "0"
CACHE_SECONDS = 600

LEVELS = ["Sector", "Industry", "Industry Group", "Industry Sub group"]
TEXT_COLS = ["Name", "BSE Code", "NSE Code", "Industry"]   # never converted to numbers

# When the results sheet uses a different name than the mapping sheet, link them here:
#   "name in results sheet": "same thing's name in the mapping sheet (any level)"
ALIASES = {
    # "IT - Software": "Computers - Software & Consulting",
    # "Finance": "Non Banking Financial Company (NBFC)",
}

COMPANY_KEY = "f_company"
FILTER_KEYS = [f"f_{level}" for level in LEVELS] + [COMPANY_KEY]

# colours: red (bad) → neutral → green (good)
NEG, MID, POS = "#DC2626", "#F3F4F6", "#16A34A"
DIVERGING = [[0.0, NEG], [0.5, MID], [1.0, POS]]
UNMAPPED = "Unmapped"

st.set_page_config(page_title="Sector Rotation", page_icon="📊", layout="wide")

# ---------------------------------------------------------------- styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(180deg, #F5F7FF 0%, #FFFFFF 60%); }
    .block-container { padding-top: 1.6rem; max-width: 1500px; }

    /* ---- sidebar: purple panel, white headings/labels ---- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #4F46E5 0%, #7C3AED 100%);
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] [role="radiogroup"] p { color: #FFFFFF !important; }

    /* ---- sidebar inputs: white box, dark text so typing is visible ---- */
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background: #FFFFFF !important;
        border: 1px solid transparent !important;
        border-radius: 10px !important;
    }
    section[data-testid="stSidebar"] div[data-baseweb="select"] input,
    section[data-testid="stSidebar"] div[data-baseweb="select"] div,
    section[data-testid="stSidebar"] div[data-baseweb="select"] span {
        color: #1F2937 !important;
        caret-color: #4F46E5 !important;
        -webkit-text-fill-color: #1F2937 !important;
    }
    section[data-testid="stSidebar"] div[data-baseweb="select"] svg { fill: #6B7280 !important; }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] { background: #EEF2FF !important; }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] span {
        color: #4338CA !important; -webkit-text-fill-color: #4338CA !important;
    }
    section[data-testid="stSidebar"] span[data-baseweb="tag"] svg { fill: #4338CA !important; }
    section[data-testid="stSidebar"] .stButton button {
        background: #FFFFFF; border: none; border-radius: 10px; width: 100%;
        font-weight: 600; color: #4F46E5;
    }
    section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.3); }

    /* ---- hero header ---- */
    .hero {
        background: linear-gradient(120deg, #4F46E5 0%, #7C3AED 55%, #EC4899 100%);
        border-radius: 20px; padding: 24px 30px; color: white;
        box-shadow: 0 12px 30px rgba(79,70,229,0.25); margin-bottom: 18px;
        display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 12px;
    }
    .hero h1 { margin: 0; font-size: 2rem; font-weight: 800; color: white; }
    .hero p  { margin: 6px 0 0; opacity: 0.9; font-size: 0.95rem; }
    .hero .chips span {
        background: rgba(255,255,255,0.18); border-radius: 999px; padding: 4px 12px;
        font-size: 0.8rem; margin-left: 6px; white-space: nowrap;
    }

    /* ---- KPI cards ---- */
    .kpi {
        background: #FFFFFF; border-radius: 16px; padding: 16px 18px; height: 100%;
        box-shadow: 0 4px 16px rgba(17,24,39,0.06); border: 1px solid #EEF0F7;
    }
    .kpi .label { color: #6B7280; font-size: 0.8rem; font-weight: 600;
                  text-transform: uppercase; letter-spacing: .04em; }
    .kpi .value { color: #111827; font-size: 1.6rem; font-weight: 700; margin-top: 4px;
                  font-variant-numeric: tabular-nums; }
    .kpi .sub   { color: #6B7280; font-size: 0.8rem; margin-top: 2px;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .kpi.accent { border-top: 4px solid #4F46E5; }
    .kpi.pink   { border-top: 4px solid #EC4899; }
    .kpi.green  { border-top: 4px solid #10B981; }
    .kpi.amber  { border-top: 4px solid #F59E0B; }
    .kpi.red    { border-top: 4px solid #DC2626; }
    .up   { color: #16A34A !important; }
    .down { color: #DC2626 !important; }

    /* ---- section titles ---- */
    .sec { font-size: 1.05rem; font-weight: 700; color: #111827; margin: 8px 0 2px; }
    .sec-sub { color: #6B7280; font-size: 0.85rem; margin-bottom: 8px; }

    /* ---- tabs ---- */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: none; }
    .stTabs [data-baseweb="tab"] {
        background: #FFFFFF; border: 1px solid #E5E7F0; border-radius: 10px;
        padding: 8px 16px; font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: #4F46E5 !important; color: #FFFFFF !important; border-color: #4F46E5;
    }
    .stTabs [aria-selected="true"] p { color: #FFFFFF !important; }
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

    /* ---- cards for charts & tables ---- */
    div[data-testid="stDataFrame"], div[data-testid="stPlotlyChart"] {
        background: #FFFFFF; border-radius: 16px; padding: 6px;
        box-shadow: 0 4px 16px rgba(17,24,39,0.06); border: 1px solid #EEF0F7;
    }
    .stDownloadButton button {
        background: linear-gradient(120deg, #4F46E5, #7C3AED); color: white;
        border: none; border-radius: 10px; font-weight: 600; padding: 0.5rem 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- loaders (unchanged)
def csv_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Fetching results sheet…")
def load_results() -> pd.DataFrame:
    return pd.read_csv(csv_url(RESULTS_SHEET_ID, RESULTS_GID), dtype=str, keep_default_na=False)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Fetching sector mapping…")
def load_mapping() -> pd.DataFrame:
    return pd.read_csv(csv_url(MAPPING_SHEET_ID, MAPPING_GID), dtype=str, keep_default_na=False)


def key(s: pd.Series) -> pd.Series:
    """Matching key: lowercase, letters/digits only (ignores spaces, dashes, odd encodings).
    'and' and '&' count as the same, so 'Oil and Gas' matches 'Oil & Gas'."""
    s = s.fillna("").astype(str).str.lower().str.replace("â€“", "-", regex=False)
    s = s.str.replace(r"\band\b", "&", regex=True)
    return s.str.replace(r"[^a-z0-9]", "", regex=True)


def clean_results(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    df = df.replace({"": pd.NA, "None": pd.NA, "#N/A": pd.NA})
    df = df.dropna(how="all").dropna(axis=1, how="all")

    rename = {c: t for c in df.columns for t in TEXT_COLS if c.lower() == t.lower()}
    df = df.rename(columns=rename)

    for col in df.columns:
        s = df[col].astype("string").str.strip()
        if col in TEXT_COLS:
            if col.endswith("Code"):
                s = s.str.replace(r"\.0$", "", regex=True)
            df[col] = s
            continue
        num = pd.to_numeric(
            s.str.replace("%", "", regex=False).str.replace(",", "", regex=False),
            errors="coerce",
        )
        if s.notna().any() and num.notna().sum() >= 0.8 * s.notna().sum():
            df[col] = num

    if "Name" in df.columns:
        df = df[~df["Name"].astype(str).str.contains("Grand Total", case=False, na=False)]
    return df.reset_index(drop=True)


def clean_mapping(m: pd.DataFrame) -> pd.DataFrame:
    m = m.copy()
    m.columns = [" ".join(str(c).split()) for c in m.columns]
    lower = {c.lower(): c for c in m.columns}
    aliases = {
        "Sector": ["sector", "sector name"],
        "Industry": ["industry", "industry name"],
        "Industry Group": ["industry group", "group name", "group"],
        "Industry Sub group": ["industry sub group", "industry subgroup", "sub group name", "sub group"],
    }
    cols = {}
    for target, names in aliases.items():
        for n in names:
            if n in lower:
                cols[lower[n]] = target
                break
    m = m.rename(columns=cols)
    missing = [c for c in LEVELS if c not in m.columns]
    if missing:
        raise ValueError(f"Mapping sheet is missing columns: {missing}")
    m = m[LEVELS].copy()
    for c in LEVELS:
        m[c] = m[c].astype(str).str.strip().str.replace("â€“", "–", regex=False)
    m = m[(m != "").all(axis=1)]
    return m.reset_index(drop=True)


def build_lookup(m: pd.DataFrame) -> pd.DataFrame:
    """One row per matching key -> Sector / Industry / Industry Group / Industry Sub group.
    The results sheet's "Industry" text is looked up at EVERY level of the mapping, lowest first."""
    parts = []
    for depth in range(len(LEVELS) - 1, -1, -1):          # Sub group → Group → Industry → Sector
        level = LEVELS[depth]
        part = m[LEVELS[: depth + 1]].copy()
        part["_key"] = key(part[level])
        part["_matched_on"] = level
        parts.append(part.drop_duplicates("_key"))
    lookup = pd.concat(parts, ignore_index=True)
    return lookup[lookup["_key"] != ""].drop_duplicates("_key")   # lowest level wins


# ---------------------------------------------------------------- load + join (unchanged)
try:
    results = clean_results(load_results())
except Exception as e:
    st.error(f"Couldn't load the results sheet: {e}")
    st.info("Share it as **Anyone with the link → Viewer** and refresh.")
    st.stop()

try:
    mapping = clean_mapping(load_mapping())
except Exception as e:
    st.error(f"Couldn't load the sector mapping sheet: {e}")
    st.info("Share the mapping sheet as **Anyone with the link → Viewer** and refresh.")
    st.stop()

if "Industry" not in results.columns:
    st.error("The results sheet has no 'Industry' column, so companies can't be mapped to sectors.")
    st.stop()
df = results.rename(columns={"Industry": "_raw"})
df = df.drop(columns=[c for c in LEVELS if c in df.columns])   # these come from the mapping
alias_key = (dict(zip(key(pd.Series(list(ALIASES), dtype=str)),
                      key(pd.Series(list(ALIASES.values()), dtype=str)))) if ALIASES else {})
df["_key"] = key(df["_raw"]).map(lambda k: alias_key.get(k, k))
df = df.merge(build_lookup(mapping), on="_key", how="left")
df["Industry Sub group"] = df["Industry Sub group"].fillna(df["_raw"])
for c in LEVELS:
    df[c] = df[c].fillna("")

NUMERIC_COLS = [c for c in df.columns
                if not c.startswith("_") and c not in TEXT_COLS + LEVELS
                and pd.api.types.is_numeric_dtype(df[c])]


# ---------------------------------------------------------------- helpers
def fmt(v, digits: int = 2, sign: bool = False) -> str:
    if v is None or pd.isna(v):
        return "–"
    return f"{v:+,.{digits}f}" if sign else f"{v:,.{digits}f}"


def color_range(s: pd.Series) -> tuple[float, float]:
    """Symmetric colour limits around 0, clipped at the 5th/95th percentile so one
    outlier (e.g. +4000 % profit growth) doesn't wash every other cell out."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return -1.0, 1.0
    lim = float(max(abs(s.quantile(0.05)), abs(s.quantile(0.95)))) or 1.0
    return -lim, lim


def short(label: str, n: int = 38) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def style_plot(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=20, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#1F2937"),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(gridcolor="#EEF0F7", zerolinecolor="#9CA3AF")
    fig.update_yaxes(gridcolor="#EEF0F7")
    return fig


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="sec">{title}</div>' + (f'<div class="sec-sub">{sub}</div>' if sub else ""),
                unsafe_allow_html=True)


def group_stats(frame: pd.DataFrame, by: str, metric: str, min_n: int) -> pd.DataFrame:
    g = frame.assign(**{by: frame[by].replace("", UNMAPPED)})
    out = g.groupby(by).agg(
        Companies=(metric, "size"),
        Reported=(metric, "count"),
        Median=(metric, "median"),
        Mean=(metric, "mean"),
        Positive=(metric, lambda s: (s > 0).sum()),
    )
    out["Breadth %"] = np.where(out["Reported"] > 0, 100 * out["Positive"] / out["Reported"], np.nan)
    out = out[out["Reported"] >= min_n].dropna(subset=["Median"])
    return out.sort_values("Median", ascending=False).reset_index()


# ---------------------------------------------------------------- sidebar: linked filters
def clear_filters():
    for k in FILTER_KEYS:
        st.session_state[k] = []


def refresh_data():
    st.cache_data.clear()


def keep_valid(state_key: str, options) -> None:
    if state_key in st.session_state:
        valid = set(options)
        st.session_state[state_key] = [v for v in st.session_state[state_key] if v in valid]


st.sidebar.markdown("## 🔎 Filters")


def linked_multiselect(level: str, frame: pd.DataFrame) -> list[str]:
    options = sorted(v for v in frame[level].dropna().unique() if v != "")
    state_key = f"f_{level}"
    keep_valid(state_key, options)
    return st.sidebar.multiselect(level, options, key=state_key, placeholder=f"All ({len(options)})")


view = df
for level in LEVELS:
    chosen = linked_multiselect(level, view)
    if chosen:
        view = view[view[level].isin(chosen)]

search_cols = [c for c in ["Name", "NSE Code", "BSE Code"] if c in view.columns]
labels = view[search_cols].fillna("").astype(str).agg(lambda r: " · ".join(v for v in r if v), axis=1)
company_options = sorted(labels.unique())
keep_valid(COMPANY_KEY, company_options)
companies = st.sidebar.multiselect(
    "Search company (name / NSE / BSE code)", company_options,
    key=COMPANY_KEY, placeholder="Type e.g. 3MINDIA or 523395",
)
if companies:
    view = view[labels.isin(companies)]

st.sidebar.markdown("---")
st.sidebar.markdown("## 📐 View")
metric = None
if NUMERIC_COLS:
    metric = st.sidebar.selectbox("Rank by metric", NUMERIC_COLS, key="v_metric",
                                  help="Drives the leaderboard, map colours, movers and KPIs.")
group_by = st.sidebar.radio("Compare groups at", LEVELS, index=0, key="v_level")
min_n = st.sidebar.slider("Min. companies per group", 1, 20, 3, key="v_min_n",
                          help="Hide groups too small for their median to mean much.")

st.sidebar.markdown("---")
c1, c2 = st.sidebar.columns(2)
c1.button("🧹 Clear", on_click=clear_filters, width="stretch")
c2.button("🔄 Refresh", on_click=refresh_data, width="stretch")

# ---------------------------------------------------------------- header
active = [f"{len(st.session_state.get(k, []))} {lvl}" for lvl, k in zip(LEVELS, FILTER_KEYS)
          if st.session_state.get(k)]
chips = "".join(f"<span>{c}</span>" for c in (active or ["No filters"]))
st.markdown(
    f"""
    <div class="hero">
      <div><h1>📊 Sector Rotation – Results Basis</h1>
           <p>Sector › Industry › Industry Group › Sub group · live from Google Sheets</p></div>
      <div class="chips">{chips}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if view.empty:
    st.warning("No companies match these filters.")
    st.stop()

# ---------------------------------------------------------------- KPIs
unmapped = int((view["Sector"] == "").sum())
cards = [
    ("accent", "Companies", f"{len(view):,}", f"{unmapped:,} unmapped" if unmapped else "all mapped"),
    ("pink", "Sectors", f"{view['Sector'].replace('', pd.NA).nunique():,}",
     f"{view['Industry'].replace('', pd.NA).nunique():,} industries"),
    ("amber", "Sub groups", f"{view['Industry Sub group'].replace('', pd.NA).nunique():,}",
     f"{view['Industry Group'].replace('', pd.NA).nunique():,} industry groups"),
]
if metric:
    s = view[metric].dropna()
    breadth = 100 * (s > 0).mean() if len(s) else np.nan
    gs = group_stats(view, "Sector", metric, 1)
    cards += [
        ("green", f"Median · {short(metric, 22)}", fmt(s.median()),
         f"{len(s):,} reported · mean {fmt(s.mean())}"),
        ("green" if (breadth or 0) >= 50 else "red", "Breadth (positive)",
         f"{fmt(breadth, 0)}%", f"{int((s > 0).sum()):,} up · {int((s <= 0).sum()):,} flat/down"),
        ("accent", "Top sector", short(gs.iloc[0]["Sector"], 18) if len(gs) else "–",
         f"median {fmt(gs.iloc[0]['Median'])}" if len(gs) else ""),
    ]
for col, (cls, label, value, sub) in zip(st.columns(len(cards)), cards):
    col.markdown(
        f'<div class="kpi {cls}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )
st.write("")

# ---------------------------------------------------------------- table prep (used by several tabs)
front = [c for c in ["Name", "BSE Code", "NSE Code"] + LEVELS if c in view.columns]
rest = [c for c in view.columns if c not in front and not c.startswith("_")]
table = view[front + rest].copy()
for c in ["Name", "BSE Code", "NSE Code"]:
    if c in table.columns:
        table[c] = table[c].fillna("")
num_cols = [c for c in NUMERIC_COLS if c in table.columns]


def styled(frame: pd.DataFrame, cols: list[str]):
    """Red→green background per numeric column, centred on 0, outliers clipped."""
    sty = frame.style.format({c: "{:,.2f}" for c in cols}, na_rep="–")
    for c in cols:
        lo, hi = color_range(frame[c])
        sty = sty.background_gradient(cmap="RdYlGn", subset=[c], vmin=lo, vmax=hi)
    return sty


tab_names = ["🏁 Leaderboard", "🔥 Heatmap", "🧭 Market map", "🚀 Movers", "📋 Companies"]
if not metric:
    tab_names = ["📋 Companies"]
tabs = dict(zip(tab_names, st.tabs(tab_names)))

# ---------------------------------------------------------------- 🏁 leaderboard
if metric:
    with tabs["🏁 Leaderboard"]:
        gs = group_stats(view, group_by, metric, min_n)
        if gs.empty:
            st.info(f"No {group_by} has at least {min_n} companies reporting {metric}. Lower the slider.")
        else:
            section(f"{group_by} ranked by median {metric}",
                    f"{len(gs)} groups with ≥ {min_n} reporting companies · "
                    "bar = median, label = breadth (% of companies positive)")
            top = gs.head(40).iloc[::-1]
            lo, hi = color_range(gs["Median"])
            fig = go.Figure(go.Bar(
                x=top["Median"], y=[short(v) for v in top[group_by]], orientation="h",
                marker=dict(color=top["Median"], colorscale=DIVERGING, cmin=lo, cmax=hi),
                text=[f"{b:.0f}% up · n={n}" for b, n in zip(top["Breadth %"], top["Reported"])],
                textposition="outside", cliponaxis=False,
                customdata=np.stack([top[group_by], top["Mean"], top["Breadth %"], top["Reported"]], axis=1),
                hovertemplate="<b>%{customdata[0]}</b><br>Median %{x:,.2f}<br>Mean %{customdata[1]:,.2f}"
                              "<br>Breadth %{customdata[2]:.0f}%<br>Companies %{customdata[3]}<extra></extra>",
            ))
            st.plotly_chart(style_plot(fig, max(320, 26 * len(top) + 60)), width="stretch")
            if len(gs) > 40:
                st.caption(f"Showing top 40 of {len(gs)} — full list below.")

            left, right = st.columns([3, 2])
            with left:
                section("Full ranking")
                show = gs[[group_by, "Companies", "Reported", "Median", "Mean", "Breadth %"]]
                st.dataframe(
                    styled(show, ["Median", "Mean"]), hide_index=True, width="stretch", height=420,
                    column_config={
                        "Breadth %": st.column_config.ProgressColumn(
                            "Breadth %", min_value=0, max_value=100, format="%.0f%%"),
                    },
                )
            with right:
                section("Strength vs breadth", "Top-right = strong and broad-based")
                sc = px.scatter(gs, x="Breadth %", y="Median", size="Reported", hover_name=group_by,
                                color="Median", color_continuous_scale=DIVERGING,
                                range_color=color_range(gs["Median"]), size_max=40)
                sc.add_vline(x=50, line_dash="dot", line_color="#9CA3AF")
                sc.add_hline(y=0, line_dash="dot", line_color="#9CA3AF")
                sc.update_layout(coloraxis_showscale=False)
                st.plotly_chart(style_plot(sc, 420), width="stretch")

    # ------------------------------------------------------------ 🔥 heatmap
    with tabs["🔥 Heatmap"]:
        default = NUMERIC_COLS[: min(10, len(NUMERIC_COLS))]
        picked = st.multiselect("Metrics (columns)", NUMERIC_COLS, default=default, key="v_heat_cols")
        if not picked:
            st.info("Pick at least one metric.")
        else:
            g = view.assign(**{group_by: view[group_by].replace("", UNMAPPED)})
            counts = g.groupby(group_by)[picked[0]].size().rename("Companies")
            med = g.groupby(group_by)[picked].median()
            hm = pd.concat([counts, med], axis=1)
            hm = hm[hm["Companies"] >= min_n].sort_values(metric if metric in picked else picked[0],
                                                          ascending=False)
            section(f"Median of each metric by {group_by}",
                    "Each column is coloured on its own scale: green = better than 0, red = worse. "
                    "Sorted by the ranking metric.")
            st.dataframe(styled(hm.reset_index(), picked), hide_index=True, width="stretch",
                         height=min(700, 38 + 35 * len(hm)))

    # ------------------------------------------------------------ 🧭 market map
    with tabs["🧭 Market map"]:
        section("Market map", f"Box size = number of companies · colour = average {metric} "
                              "· click a box to zoom in, click the top bar to zoom out")
        tm = view[LEVELS + [metric]].copy()
        for c in LEVELS:
            tm[c] = tm[c].replace("", UNMAPPED)
        tm["_n"] = 1
        lo, hi = color_range(tm[metric])
        tm["_c"] = tm[metric].clip(lo, hi)
        tm = tm.dropna(subset=["_c"])
        if tm.empty:
            st.info(f"No company in this view reports {metric}.")
        else:
            fig = px.treemap(tm, path=[px.Constant("All")] + LEVELS, values="_n", color="_c",
                             color_continuous_scale=DIVERGING, range_color=(lo, hi),
                             color_continuous_midpoint=0)
            fig.update_traces(
                hovertemplate="<b>%{label}</b><br>Companies %{value}<br>Avg " + metric +
                              " %{color:,.2f}<extra></extra>",
                texttemplate="<b>%{label}</b><br>%{value} cos · %{color:,.1f}",
                marker=dict(cornerradius=4), root_color="#F5F7FF",
            )
            fig.update_layout(coloraxis_colorbar=dict(title="", thickness=12))
            st.plotly_chart(style_plot(fig, 640), width="stretch")
            st.caption("Colours are clipped at the 5th/95th percentile so outliers don't dominate.")

    # ------------------------------------------------------------ 🚀 movers
    with tabs["🚀 Movers"]:
        n_top = st.slider("How many", 5, 50, 15, key="v_ntop")
        cols_show = [c for c in ["Name", "NSE Code", "Sector", "Industry Sub group", metric]
                     if c in table.columns]
        ranked = table.dropna(subset=[metric]).sort_values(metric, ascending=False)
        a, b = st.columns(2)
        for col, title, part, cls in [
            (a, f"▲ Top {n_top} by {metric}", ranked.head(n_top), "up"),
            (b, f"▼ Bottom {n_top} by {metric}", ranked.tail(n_top).iloc[::-1], "down"),
        ]:
            with col:
                st.markdown(f'<div class="sec {cls}">{title}</div>', unsafe_allow_html=True)
                st.dataframe(styled(part[cols_show], [metric]), hide_index=True, width="stretch",
                             height=38 + 35 * len(part),
                             column_config={"Name": st.column_config.TextColumn("Name", pinned=True)})

        section(f"Distribution of {metric}", "Where most companies sit · dotted line = 0")
        lo, hi = color_range(ranked[metric])
        span = (hi - lo) * 0.25
        h = ranked[metric].clip(lo - span, hi + span)
        hist = px.histogram(h, nbins=50)
        hist.update_traces(marker_color="#6366F1", hovertemplate="%{x}<br>%{y} companies<extra></extra>")
        hist.add_vline(x=0, line_dash="dot", line_color="#111827")
        hist.add_vline(x=ranked[metric].median(), line_color="#EC4899",
                       annotation_text=f"median {fmt(ranked[metric].median())}",
                       annotation_position="top")
        hist.update_layout(showlegend=False, xaxis_title=metric, yaxis_title="Companies", bargap=0.05)
        st.plotly_chart(style_plot(hist, 320), width="stretch")
        st.caption("Extreme values are grouped at the edges of the chart.")

# ---------------------------------------------------------------- 📋 companies
with tabs["📋 Companies"]:
    q1, q2, q3 = st.columns([2, 2, 1])
    sort_options = ["(sheet order)"] + num_cols + [c for c in ["Name", "Sector"] if c in table.columns]
    sort_by = q1.selectbox("Sort by", sort_options,
                           index=sort_options.index(metric) if metric in sort_options else 0,
                           key="v_sort")
    hide_cols = q2.multiselect("Hide columns", [c for c in table.columns if c != "Name"], key="v_hide")
    colour = q3.toggle("Colour cells", value=True, key="v_colour")

    t = table.drop(columns=hide_cols)
    if sort_by != "(sheet order)":
        t = t.sort_values(sort_by, ascending=sort_by in ("Name", "Sector"), na_position="last")
    shown_num = [c for c in num_cols if c in t.columns]
    cfg = {c: st.column_config.NumberColumn(c, format="%.2f") for c in shown_num}
    if "Name" in t.columns:
        cfg["Name"] = st.column_config.TextColumn("Name", pinned=True)
    data = styled(t, shown_num) if colour and len(t) * max(1, len(shown_num)) <= 200_000 else t
    st.dataframe(data, width="stretch", hide_index=True, height=620, column_config=cfg)
    st.caption(f"{len(t):,} rows × {len(t.columns)} columns · green = above 0, red = below 0")
    st.download_button("⬇️ Download filtered CSV", t.to_csv(index=False),
                       "sector_rotation_filtered.csv", "text/csv")