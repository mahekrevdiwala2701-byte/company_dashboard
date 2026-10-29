"""
Streamlit app: Sector Rotation – Results Basis.

Data:
  • Results sheet   – one row per company (its "Industry" column = sub group)
  • Mapping sheet   – Sector › Industry › Industry Group › Industry Sub group
Both sheets must be shared as "Anyone with the link → Viewer".

Run:  streamlit run app.py
"""

import pandas as pd
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

st.set_page_config(page_title="Sector Rotation", page_icon="📊", layout="wide")

# ---------------------------------------------------------------- styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
    .stApp { background: linear-gradient(180deg, #F5F7FF 0%, #FFFFFF 60%); }
    .block-container { padding-top: 2rem; max-width: 1400px; }

    /* ---- sidebar: purple panel, white headings/labels ---- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #4F46E5 0%, #7C3AED 100%);
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    section[data-testid="stSidebar"] .stMarkdown p { color: #FFFFFF !important; }

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
    /* selected chips */
    section[data-testid="stSidebar"] span[data-baseweb="tag"] {
        background: #EEF2FF !important;
    }
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
        border-radius: 20px; padding: 28px 32px; color: white;
        box-shadow: 0 12px 30px rgba(79,70,229,0.25); margin-bottom: 24px;
    }
    .hero h1 { margin: 0; font-size: 2.1rem; font-weight: 800; color: white; }
    .hero p  { margin: 6px 0 0; opacity: 0.9; font-size: 1rem; }

    /* ---- KPI cards ---- */
    .kpi {
        background: #FFFFFF; border-radius: 16px; padding: 18px 20px;
        box-shadow: 0 4px 16px rgba(17,24,39,0.06); border: 1px solid #EEF0F7;
    }
    .kpi .label { color: #6B7280; font-size: 0.85rem; font-weight: 500; }
    .kpi .value { color: #111827; font-size: 1.7rem; font-weight: 700; margin-top: 4px; }
    .kpi.accent { border-top: 4px solid #4F46E5; }
    .kpi.pink   { border-top: 4px solid #EC4899; }
    .kpi.green  { border-top: 4px solid #10B981; }
    .kpi.amber  { border-top: 4px solid #F59E0B; }

    /* ---- table card ---- */
    div[data-testid="stDataFrame"] {
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


# ---------------------------------------------------------------- loaders
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

    The results sheet's "Industry" text is looked up at EVERY level of the mapping, lowest first:
    Sub group, then Industry Group, then Industry, then Sector. So a company whose results row
    says "Capital Markets" is mapped even when "Capital Markets" sits in the mapping's
    Industry Group (or Industry) column instead of its Sub group column.
    """
    parts = []
    for depth in range(len(LEVELS) - 1, -1, -1):          # Sub group → Group → Industry → Sector
        level = LEVELS[depth]
        part = m[LEVELS[: depth + 1]].copy()
        part["_key"] = key(part[level])
        part["_matched_on"] = level
        parts.append(part.drop_duplicates("_key"))
    lookup = pd.concat(parts, ignore_index=True)
    return lookup[lookup["_key"] != ""].drop_duplicates("_key")   # lowest level wins


# ---------------------------------------------------------------- load + join
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

# the results sheet's "Industry" column holds the sub group -> map it up the hierarchy
if "Industry" not in results.columns:
    st.error("The results sheet has no 'Industry' column, so companies can't be mapped to sectors.")
    st.stop()
df = results.rename(columns={"Industry": "_raw"})
df = df.drop(columns=[c for c in LEVELS if c in df.columns])   # these come from the mapping
alias_key = (dict(zip(key(pd.Series(list(ALIASES), dtype=str)),
                      key(pd.Series(list(ALIASES.values()), dtype=str)))) if ALIASES else {})
df["_key"] = key(df["_raw"]).map(lambda k: alias_key.get(k, k))
df = df.merge(build_lookup(mapping), on="_key", how="left")
# matched on a higher level (e.g. Industry Group): the company's own text is its sub group
df["Industry Sub group"] = df["Industry Sub group"].fillna(df["_raw"])
# no match (e.g. the Industry cell is empty in the results sheet): leave the cells blank,
# exactly as in the Google Sheet
for c in LEVELS:
    df[c] = df[c].fillna("")


# ---------------------------------------------------------------- sidebar: linked filters
def clear_filters():
    """Runs BEFORE the page is redrawn (on_click callback), so every box comes back empty."""
    for k in FILTER_KEYS:
        st.session_state[k] = []


def refresh_data():
    st.cache_data.clear()


def keep_valid(state_key: str, options) -> None:
    """Drop earlier picks that are no longer in the options (e.g. a parent filter changed)."""
    if state_key in st.session_state:
        valid = set(options)
        st.session_state[state_key] = [v for v in st.session_state[state_key] if v in valid]


st.sidebar.markdown("## 🔎 Filters")


def linked_multiselect(level: str, frame: pd.DataFrame) -> list[str]:
    """Multiselect whose options come only from rows left after the parent filters."""
    options = sorted(v for v in frame[level].dropna().unique() if v != "")
    state_key = f"f_{level}"
    keep_valid(state_key, options)
    return st.sidebar.multiselect(
        level, options, key=state_key, placeholder=f"All ({len(options)})"
    )


view = df
for level in LEVELS:
    chosen = linked_multiselect(level, view)
    if chosen:
        view = view[view[level].isin(chosen)]

st.sidebar.markdown("---")

search_cols = [c for c in ["Name", "NSE Code", "BSE Code"] if c in view.columns]
labels = view[search_cols].fillna("").astype(str).agg(
    lambda r: " · ".join(v for v in r if v), axis=1
)
company_options = sorted(labels.unique())
keep_valid(COMPANY_KEY, company_options)
companies = st.sidebar.multiselect(
    "Search company (name / NSE / BSE code)",
    company_options,
    key=COMPANY_KEY,
    placeholder="Type e.g. 3MINDIA or 523395",
)
if companies:
    view = view[labels.isin(companies)]

st.sidebar.markdown("---")
c1, c2 = st.sidebar.columns(2)
c1.button("🧹 Clear", on_click=clear_filters, use_container_width=True)
c2.button("🔄 Refresh", on_click=refresh_data, use_container_width=True)

# ---------------------------------------------------------------- header + KPIs
st.markdown(
    """
    <div class="hero">
      <h1>📊 Sector Rotation – Results Basis</h1>
      <p>Sector › Industry › Industry Group › Sub group · live from Google Sheets</p>
    </div>
    """,
    unsafe_allow_html=True,
)

cards = [
    ("accent", "Companies", f"{len(view):,}"),
    ("pink", "Sectors", f"{view['Sector'].replace('', pd.NA).nunique():,}"),
    ("green", "Industries", f"{view['Industry'].replace('', pd.NA).nunique():,}"),
    ("amber", "Sub groups", f"{view['Industry Sub group'].replace('', pd.NA).nunique():,}"),
]
for col, (cls, label, value) in zip(st.columns(4), cards):
    col.markdown(
        f'<div class="kpi {cls}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div></div>',
        unsafe_allow_html=True,
    )
st.write("")

# ---------------------------------------------------------------- table
front = [c for c in ["Name", "BSE Code", "NSE Code"] + LEVELS if c in view.columns]
rest = [c for c in view.columns if c not in front and not c.startswith("_")]
table = view[front + rest].copy()
for c in ["Name", "BSE Code", "NSE Code"]:          # show blanks instead of "None"
    if c in table.columns:
        table[c] = table[c].fillna("")

if table.empty:
    st.warning("No companies match these filters.")
else:
    col_cfg = {
        c: st.column_config.NumberColumn(c, format="%.2f")
        for c in table.columns if pd.api.types.is_numeric_dtype(table[c])
    }
    col_cfg["Name"] = st.column_config.TextColumn("Name", pinned=True)
    st.dataframe(table, width="stretch", hide_index=True, height=600, column_config=col_cfg)
    st.caption(f"{len(table):,} rows × {len(table.columns)} columns")
    st.download_button(
        "⬇️ Download filtered CSV",
        table.to_csv(index=False),
        "sector_rotation_filtered.csv",
        "text/csv",
    )