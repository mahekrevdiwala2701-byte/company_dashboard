"""Loading, cleaning and sector mapping. No UI code here."""

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


# ---------------------------------------------------------------- loaders
def csv_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_results() -> pd.DataFrame:
    return pd.read_csv(csv_url(RESULTS_SHEET_ID, RESULTS_GID), dtype=str, keep_default_na=False)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
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


# ---------------------------------------------------------------- the one function the app uses
class DataError(Exception):
    """Raised with a user-friendly message when a sheet can't be used."""


@st.cache_data(ttl=CACHE_SECONDS, show_spinner="Loading data from Google Sheets…")
def get_data() -> tuple[pd.DataFrame, list[str]]:
    """Returns (companies joined with Sector › Industry › Group › Sub group, numeric column names).
    Cached: the sheets are downloaded and processed once every CACHE_SECONDS, not on every click."""
    try:
        results = clean_results(load_results())
    except Exception as e:
        raise DataError(f"Couldn't load the results sheet: {e}") from e
    try:
        mapping = clean_mapping(load_mapping())
    except Exception as e:
        raise DataError(f"Couldn't load the sector mapping sheet: {e}") from e
    if "Industry" not in results.columns:
        raise DataError("The results sheet has no 'Industry' column, so companies can't be mapped.")

    df = results.rename(columns={"Industry": "_raw"})
    df = df.drop(columns=[c for c in LEVELS if c in df.columns])   # these come from the mapping
    alias_key = (dict(zip(key(pd.Series(list(ALIASES), dtype=str)),
                          key(pd.Series(list(ALIASES.values()), dtype=str)))) if ALIASES else {})
    df["_key"] = key(df["_raw"]).map(lambda k: alias_key.get(k, k))
    df = df.merge(build_lookup(mapping), on="_key", how="left")
    # matched on a higher level (e.g. Industry Group): the company's own text is its sub group
    df["Industry Sub group"] = df["Industry Sub group"].fillna(df["_raw"])
    for c in LEVELS:
        df[c] = df[c].fillna("")
    for c in ["Name", "BSE Code", "NSE Code"]:
        if c in df.columns:
            df[c] = df[c].fillna("")

    # lower-case "name nse bse" text, built once, so the company search is instant
    search_cols = [c for c in ["Name", "NSE Code", "BSE Code"] if c in df.columns]
    df["_search"] = df[search_cols].astype(str).agg(" ".join, axis=1).str.lower()

    numeric = [c for c in df.columns
               if not c.startswith("_") and c not in TEXT_COLS + LEVELS
               and pd.api.types.is_numeric_dtype(df[c])]
    return df, numeric