"""🧮 Calculator page: one formula box for arithmetic on several columns, worked out for every quarter.

Nothing is shown until you press Calculate. Then you get
  * a table like the main dashboard: Sector › Industry Group › companies (click to open), one column per
    quarter, highest first (sorted on the latest quarter, at every level), Grand Total at the bottom
  * a line graph of the same numbers: pick the sectors / groups / companies to draw

How the formula box works (same rules as the pivot's Calculated field, plus quarter names)
  'Sales', 'PAT', 'OPM' …    a quarter column WITHOUT a quarter = that column for every quarter,
                             e.g. ='PAT' / 'Sales'  →  PAT Q1 FY25 / Sales Q1 FY25, then Q2 FY25, …
  'Sales prev'               the same column one quarter earlier, e.g. =('Sales' / 'Sales prev') - 1
  'Sales Q1 FY25'            with "Roll quarter columns forward" ON (default): read relative to the latest
                             quarter in the formula and moved forward one quarter at a time, so
                             ='EBIT Q1 FY25' / 'PAT Q1 FY25' gives EBIT / PAT for EVERY quarter, and
                             ='Sales Q2 FY25' / 'Sales Q1 FY25' - 1 gives growth vs the previous quarter.
                             OFF: a fixed column (the same number on every quarter → a flat line)
  + − × ÷ ^ %, brackets, and every function in the pivot's Function list (ROUND, IF, AVERAGE …)

A sector / group value is worked out like the pivot: each column is first summarised for the group
(SUM by default), then the formula runs, e.g. SUM of PAT ÷ SUM of Sales.
"""

import json
import re

import altair as alt
import pandas as pd
import streamlit as st

import pivot
import ui
from data import LEVELS

ss = st.session_state
COMPANY = "Company"
OPERATORS = ["+", "−", "×", "÷", "^", "(", ")", ","]
FN_HELP = {name: helptext for name, _, helptext in pivot.FUNCTIONS}
FN_INSERT = {name: ins for name, ins, _ in pivot.FUNCTIONS}
MAX_LINES = 12
DEFAULT_LINES = 5
FONT = "Plus Jakarta Sans, Segoe UI, Arial, sans-serif"
KEEP = ["calc_s", "calc_same", "calc_fmt", "calc_dec", "calc_levels", "calc_run", "calc_roll",
        "calc_qids", "calc_next", "calc_quarters", "calc_rowfilter", "calc_colmode", "calc_collevel",
        "calc_colfilter", "calc_extra"]
COL_QUARTERS, COL_CALCS, COL_GROUPS = "Quarters", "Calculations side by side", "Sector / Industry / Group"
MAX_COLS = 150
KEEP_PREFIX = ("cq_", "calc_pick_", "calc_line_lv_")              # per-calculation widgets
CUSTOM = "✏️ Custom formula"
# operation → (formula pattern, needs a second column, plain-English meaning)
SIMPLE_OPS = {
    "÷  Divide": ("='{a}' / '{b}'", True, "{A} ÷ {B}"),
    "−  Minus": ("='{a}' - '{b}'", True, "{A} − {B}"),
    "+  Plus": ("='{a}' + '{b}'", True, "{A} + {B}"),
    "×  Times": ("='{a}' * '{b}'", True, "{A} × {B}"),
    "Growth vs previous quarter": ("=('{a}' / '{a} prev') - 1", False, "{A} growth vs previous quarter"),
    "Just show the column": ("='{a}'", False, "{A}"),
    CUSTOM: (None, False, None),
}
EXAMPLES = {
    "PAT margin": "='PAT' / 'Sales'",
    "Sales growth vs previous quarter": "=('Sales' / 'Sales prev') - 1",
    "PAT growth vs previous quarter": "=('PAT' / 'PAT prev') - 1",
    "Operating profit share of EBIT": "='OP' / 'EBIT'",
    "Sales − OP (costs)": "='Sales' - 'OP'",
}
PALETTE = ["#0F766E", "#0284C7", "#D97706", "#E11D48", "#65A30D", "#7C3AED",
           "#0891B2", "#EA580C", "#DB2777", "#16A34A", "#CA8A04", "#2563EB"]


# ---------------------------------------------------------------- quarters in the sheet
def _label(metric: str) -> str:
    """SALES → Sales, SALES GROWTH → Sales Growth, OPM / PAT stay as they are."""
    return " ".join(w.title() if w in ("SALES", "GROWTH") else w for w in metric.split())


def quarter_info(numeric: list[str]):
    """({metric: {(fy, q): column}}, [(fy, q) in time order]) from columns like 'PAT Q2 FY26'."""
    by_metric: dict[str, dict[tuple, str]] = {}
    for (metric, fy, q), col in pivot._quarter_columns(numeric).items():
        by_metric.setdefault(metric, {})[(fy, q)] = col
    quarters = sorted({fq for cols in by_metric.values() for fq in cols})
    return by_metric, quarters


def qname(fq: tuple) -> str:
    return f"Q{fq[1]} FY{fq[0]:02d}"


_NORM = re.compile(r"\s+")


def _norm(name: str) -> str:
    return _NORM.sub("", name).upper()


def _fixed_quarter_refs(text: str, by_metric: dict, quarters: list) -> dict:
    """{'ebit q1 fy25': (metric, index of that quarter)} for every fixed quarter column in the formula."""
    reverse = {col.strip().lower(): (metric, quarters.index(fq))
               for metric, cols in by_metric.items() for fq, col in cols.items() if fq in quarters}
    out = {}
    for n in pivot._REF.findall(text or ""):
        key = n.replace("''", "'").strip().lower()
        if key in reverse:
            out[key] = reverse[key]
    return out


def for_quarter(text: str, by_metric: dict, quarters: list, i: int, roll: bool = False):
    """The formula with every quarter name ('PAT', 'Sales prev') swapped for that quarter's real column.
    roll = True: fixed quarter columns ('PAT Q1 FY25') move too, relative to the latest one in the formula.
    Returns (formula text, missing names) — missing = that quarter has no such column."""
    metrics = {_norm(m): m for m in by_metric}
    fixed = _fixed_quarter_refs(text, by_metric, quarters) if roll else {}
    anchor = max((k for _, k in fixed.values()), default=0)
    missing = []

    def swap(m):
        name = m.group(1).replace("''", "'").strip()
        if name.lower() in fixed:                                # 'PAT Q1 FY25' rolled to this quarter
            metric, k = fixed[name.lower()]
            j = i - (anchor - k)
            col = by_metric[metric].get(quarters[j]) if j >= 0 else None
            if col is None:
                missing.append(name)
                return m.group(0)
            return "'" + col.replace("'", "''") + "'"
        key, back = _norm(name), 0
        for suffix in ("PREVIOUS", "PREV"):
            if key.endswith(suffix) and key[: -len(suffix)] in metrics:
                key, back = key[: -len(suffix)], 1
                break
        if key not in metrics:
            return m.group(0)                                    # a normal sheet column: leave it
        j = i - back
        col = by_metric[metrics[key]].get(quarters[j]) if j >= 0 else None
        if col is None:
            missing.append(name)
            return m.group(0)
        return "'" + col.replace("'", "''") + "'"

    return pivot._REF.sub(swap, text or ""), missing


def uses_quarters(text: str, by_metric: dict, quarters: list | None = None, roll: bool = False) -> bool:
    if roll and quarters and _fixed_quarter_refs(text, by_metric, quarters):
        return True
    metrics = {_norm(m) for m in by_metric}
    names = [_norm(n.replace("''", "'")) for n in pivot._REF.findall(text or "")]
    return any(n in metrics or any(n == m + s for m in metrics for s in ("PREV", "PREVIOUS")) for n in names)


# ---------------------------------------------------------------- the maths
AUTO = "Auto"
# margins / growth / deltas are ratios: for a group they are averaged, never added up
_RATIO = re.compile(r"^(OPM|EBIT\s?M)\b|growth|delta|margin", re.I)
_AGG_BEFORE = re.compile(r"\b(?:" + "|".join(pivot.SUMMARIZE) + r")\s*\(\s*$", re.I)


def is_ratio(col: str) -> bool:
    return bool(_RATIO.search(col.strip()))


def _resolve(m, lookup: dict) -> str | None:
    return lookup.get(m.group(1).replace("''", "'").strip().lower())


def _quote(col: str) -> str:
    return "'" + col.replace("'", "''") + "'"


def _auto_summary(text: str, lookup: dict) -> str:
    """Auto: margin / growth columns → AVERAGE('col'), money columns stay SUM (the default)."""
    out, last = [], 0
    for m in pivot._REF.finditer(text):
        col = _resolve(m, lookup)
        out.append(text[last:m.start()])
        if col and is_ratio(col) and not _AGG_BEFORE.search(text[:m.start()]):
            out.append(f"AVERAGE({m.group(0)})")
        else:
            out.append(m.group(0))
        last = m.end()
    return "".join(out) + text[last:]


def auto_format(text: str, used: set[str]) -> str:
    """Percent for ratios (a division, or only margin / growth columns), Number for amounts."""
    bare = pivot._REF.sub("x", text or "")
    if "/" in bare or "÷" in bare or "DIVIDE(" in bare.upper():
        return "percent"
    return "percent" if used and all(is_ratio(c) for c in used) else "number"


def prepare(view: pd.DataFrame, numeric: list[str], text: str, summarize: str, fmt: str, dec: int,
            same: bool, roll: bool = True, row_mask: pd.Series | None = None, tag: str = ""):
    """One pivot value per quarter (a formula with that quarter's columns).
    same = True: in each quarter only companies that have EVERY number the formula needs, and a result
    (Sales not 0 — the sheet puts 0 in every column when a company has no result), are counted, so a
    group's total ÷ total (or average) compares like with like.
    Returns (values, extra columns for the view, first error or None, format used)."""
    by_metric, quarters = quarter_info(numeric)
    columns = pivot.formula_columns(numeric)
    lookup = {c.lower(): c for c in columns}
    values, extra, error, used_all = [], {}, None, set()
    how = "SUM" if summarize == AUTO else summarize
    sales_cols = by_metric.get("SALES", {})
    for i, fq in enumerate(quarters):
        text_q, missing = for_quarter(text, by_metric, quarters, i, roll)
        if missing:
            continue
        if summarize == AUTO:
            text_q = _auto_summary(text_q, lookup)
        try:
            f = pivot.compile_formula(text_q, columns, how)
        except pivot.FormulaError as e:
            error = error or str(e)
            continue
        used = {c for c, _ in f.cols.values() if c in view.columns and pd.api.types.is_numeric_dtype(view[c])}
        used_all |= used
        if (same or row_mask is not None or tag) and used:
            # row_mask = only these companies count (e.g. one sector, when sectors are the columns)
            ok = row_mask.reindex(view.index, fill_value=False) if row_mask is not None \
                else pd.Series(True, index=view.index)
            if same:
                touched = set()
                for c in used:
                    ok &= pd.to_numeric(view[c], errors="coerce").notna()
                    touched |= {(fy, q) for (_, fy, q) in pivot._quarter_columns([c])}
                for fyq in touched:                              # no Sales that quarter = no result yet
                    sales = sales_cols.get(fyq)
                    if sales in view.columns:
                        s = pd.to_numeric(view[sales], errors="coerce")
                        ok &= s.notna() & s.ne(0)
            names = {}
            for c in used:
                names[c] = f"{c} ‹{tag}{qname(fq)}›"
                extra[names[c]] = pd.to_numeric(view[c], errors="coerce").where(ok)
            text_q = pivot._REF.sub(lambda m: _quote(names[_resolve(m, lookup)])
                                    if _resolve(m, lookup) in names else m.group(0), text_q)
        values.append({"id": f"q{fq[0]}{fq[1]}", "name": qname(fq), "formula": text_q})
    out_fmt = auto_format(text, used_all) if fmt == AUTO else fmt
    values = [pivot.value_defaults({**v, "summarize": how, "format": out_fmt, "decimals": dec}) for v in values]
    return values, pd.DataFrame(extra, index=view.index), error, out_fmt


def _layout(values: list[dict], levels: list[str], sort_by: str) -> dict:
    sort = {lv: {"by": sort_by, "dir": "desc"} for lv in levels + [COMPANY]}
    return {"name": "Calculator", "levels": levels, "values": values, "filters": [], "sort": sort,
            "grand_total": True}


@st.cache_data(ttl=600, max_entries=30, show_spinner=False)
def _tree(view: pd.DataFrame, values_json: str, levels: tuple, columns: tuple, n_sort: int = 0) -> dict:
    """The result as the dashboard's tree, highest first on the last column that has a value.
    n_sort = how many of the values may be sorted on (0 = all; extra sheet columns come after them)."""
    values = json.loads(values_json)
    n = n_sort or len(values)
    tree = pivot.build_tree(view, _layout(values, list(levels), values[n - 1]["name"]), list(columns))
    total = ((tree.get("total") or {}).get("vals") or [])[:n]
    have = [i for i, v in enumerate(total) if v is not None]
    if have and have[-1] != n - 1:                              # newest column is empty: sort on the last full one
        tree = pivot.build_tree(view, _layout(values, list(levels), values[have[-1]]["name"]), list(columns))
    return tree


@st.cache_data(ttl=600, max_entries=30, show_spinner=False)
def _page(tree_json: str, height: int, style: str) -> str:
    """style = ui.STYLE_VERSION so a look change is never served from an old cache."""
    return ui.pivot_html(json.loads(tree_json), height)


def line_table(tree: dict, level: str) -> pd.DataFrame:
    """Rows of one level of the tree (a sector level or Company) → DataFrame (line × quarter)."""
    levels = tree["levels"]
    depth = levels.index(level) if level in levels else len(levels)
    rows, labels = [], []

    def walk(items, d, parent):
        for r in items:
            if "kids" in r:
                if d == depth:
                    rows.append(r["vals"])
                    labels.append((str(r["label"]), parent))
                else:
                    walk(r["kids"], d + 1, str(r["label"]))
            elif depth == len(levels):
                code = str(r.get("code") or "").strip()
                rows.append(r["vals"])
                labels.append((f"{r['label']} ({code})" if code else str(r["label"]), parent))

    walk(tree["rows"], 0, "")
    names = [lab for lab, _ in labels]
    seen = {n: names.count(n) for n in names}
    names = [f"{lab} · {par}" if seen[lab] > 1 and par else lab for lab, par in labels]   # same name twice
    out = pd.DataFrame(rows, index=names, columns=tree["metrics"], dtype=float)
    return out[~out.index.duplicated()]


# ---------------------------------------------------------------- the list of calculations
def _k(qid: int, part: str) -> str:
    return f"cq_{qid}_{part}"


def _add_query(a: str | None = None, op: str | None = None, b: str | None = None) -> None:
    qid = ss.get("calc_next", 1)
    ss["calc_next"] = qid + 1
    cols = ss.get("_calc_cols") or []
    ss[_k(qid, "a")] = a or (cols[0] if cols else "")
    ss[_k(qid, "op")] = op or list(SIMPLE_OPS)[0]
    ss[_k(qid, "b")] = b or (cols[min(1, len(cols) - 1)] if cols else "")
    ss[_k(qid, "f")] = ""
    ss[_k(qid, "name")] = ""
    ss["calc_qids"] = list(ss.get("calc_qids") or []) + [qid]


def _remove_query(qid: int) -> None:
    ss["calc_qids"] = [q for q in ss.get("calc_qids") or [] if q != qid]
    for k in [k for k in ss if str(k).startswith(f"cq_{qid}_") or k in (f"calc_pick_{qid}", f"calc_line_lv_{qid}")]:
        del ss[k]


def _query_text(qid: int) -> str:
    op = ss.get(_k(qid, "op"))
    if op == CUSTOM:
        t = (ss.get(_k(qid, "f")) or "").strip()
        return "" if t in ("", "=") else (t if t.startswith("=") else "=" + t)
    a, b = ss.get(_k(qid, "a")), ss.get(_k(qid, "b"))
    if not a or op not in SIMPLE_OPS:
        return ""
    pattern, needs_b, _ = SIMPLE_OPS[op]
    if needs_b and not b:
        return ""
    return pattern.format(a=a.replace("'", "''"), b=(b or "").replace("'", "''"))


def _query_label(qid: int) -> str:
    name = (ss.get(_k(qid, "name")) or "").strip()
    if name:
        return name
    op = ss.get(_k(qid, "op"))
    if op == CUSTOM or op not in SIMPLE_OPS:
        return _query_text(qid).lstrip("=") or "Custom formula"
    return SIMPLE_OPS[op][2].format(A=ss.get(_k(qid, "a")), B=ss.get(_k(qid, "b")) or "?")


def _clear() -> None:
    for qid in list(ss.get("calc_qids") or []):
        _remove_query(qid)
    ss["calc_run"] = None
    _add_query("EBIT" if "EBIT" in (ss.get("_calc_cols") or []) else None, None,
               "PAT" if "PAT" in (ss.get("_calc_cols") or []) else None)


def _settings() -> dict:
    queries = [{"id": q, "text": _query_text(q), "label": _query_label(q)} for q in ss.get("calc_qids") or []]
    return {"queries": [q for q in queries if q["text"]],
            "summarize": ss["calc_s"],
            "fmt": {"Percent": "percent", "Number": "number"}.get(ss["calc_fmt"], AUTO),
            "dec": int(ss["calc_dec"]), "same": bool(ss.get("calc_same", True)),
            "roll": bool(ss.get("calc_roll", True)),
            "levels": [lv for lv in LEVELS if lv in (ss.get("calc_levels") or [])] or ["Sector"],
            "quarters": list(ss.get("calc_quarters") or []),
            "rowfilter": list(ss.get("calc_rowfilter") or []),
            "colmode": ss.get("calc_colmode") or COL_QUARTERS,
            "collevel": ss.get("calc_collevel"),
            "colfilter": list(ss.get("calc_colfilter") or []),
            "extra": list(ss.get("calc_extra") or [])}


def _calculate() -> None:
    ss["calc_run"] = _settings()
    for k in [k for k in ss if str(k).startswith("calc_pick_")]:
        ss[k] = None                                             # fresh lines for the new result


def _keep_values() -> None:
    """Streamlit forgets a widget's value when you visit another page: bring it back."""
    for k in list(ss.keys()):
        if str(k).startswith("_keep_"):
            name = str(k)[len("_keep_"):]
            if name not in ss:
                ss[name] = ss[k]


def _remember() -> None:
    for k in list(ss.keys()):
        k = str(k)
        if k in KEEP or k.startswith(KEEP_PREFIX):
            ss[f"_keep_{k}"] = ss[k]
    for k in [k for k in ss if str(k).startswith("_keep_cq_")]:   # removed calculations stay removed
        if str(k)[len("_keep_"):] not in ss:
            del ss[k]


# ---------------------------------------------------------------- page
def render() -> None:
    try:
        _render()
    finally:
        _remember()


def _render() -> None:
    ctx = ss["ctx"]
    view, numeric = ctx["view"], ctx["numeric"]
    by_metric, quarters = quarter_info(numeric)
    _keep_values()
    if not quarters:
        st.warning("No quarter columns found (like 'Sales Q1 FY25'), so there is nothing to work out per quarter.")
        return
    col_names = [_label(m) for m in by_metric]                   # Sales, OP, OPM, EBIT, EBITM, PAT, … Growth
    ss["_calc_cols"] = col_names
    all_q = [qname(fq) for fq in quarters]
    levels_here = [lv for lv in LEVELS if lv in view.columns]
    ss.setdefault("calc_s", AUTO)
    ss.setdefault("calc_fmt", AUTO)
    ss.setdefault("calc_same", True)
    ss.setdefault("calc_roll", True)
    ss.setdefault("calc_dec", 2)
    ss.setdefault("calc_levels", [lv for lv in ["Sector", "Industry Group"] if lv in levels_here] or levels_here[:1])
    ss.setdefault("calc_run", None)
    ss.setdefault("calc_quarters", all_q)
    ss.setdefault("calc_rowfilter", [])
    ss.setdefault("calc_colmode", COL_QUARTERS)
    ss.setdefault("calc_extra", [])
    ss["calc_levels"] = [lv for lv in ss["calc_levels"] if lv in levels_here]
    ss["calc_quarters"] = [q for q in ss["calc_quarters"] if q in all_q]
    if not ss.get("calc_qids"):
        _add_query("EBIT" if "EBIT" in col_names else None, None, "PAT" if "PAT" in col_names else None)

    with st.container(key="calcbox"):
        # ---- 1. what to calculate
        ui.section("🧮 1 · What to calculate", "Add as many calculations as you like — each gets its own table and graph")
        for n, qid in enumerate(list(ss["calc_qids"]), 1):
            for part, choices in (("a", col_names), ("b", col_names), ("op", list(SIMPLE_OPS))):
                if ss.get(_k(qid, part)) not in choices:
                    ss[_k(qid, part)] = choices[0]
            op = ss[_k(qid, "op")]
            r = st.columns([0.25, 2, 2, 2, 2, 0.45], vertical_alignment="bottom")
            r[0].markdown(f"**{n}.**")
            r[2].selectbox("Operation", list(SIMPLE_OPS), key=_k(qid, "op"))
            if op == CUSTOM:
                r[1].text_input("Formula", key=_k(qid, "f"), placeholder="='PAT' / 'Sales'",
                                help="Use column names in quotes: 'Sales', 'OP', 'EBIT', 'PAT', 'OPM' … "
                                     "Add **prev** for the previous quarter, e.g. =('PAT' / 'PAT prev') - 1. "
                                     "+ − × ÷ ( ) and functions like ROUND, IF, AVERAGE work.")
                r[3].caption("Columns: " + ", ".join(col_names))
            else:
                r[1].selectbox("Column", col_names, key=_k(qid, "a"))
                r[3].selectbox("Second column", col_names, key=_k(qid, "b"), disabled=not SIMPLE_OPS[op][1])
            r[4].text_input("Name (optional)", key=_k(qid, "name"), placeholder=_query_label(qid))
            r[5].button("", icon=":material/delete:", key=f"cq_del_{qid}", help="Remove this calculation",
                        on_click=_remove_query, args=(qid,), disabled=len(ss["calc_qids"]) == 1)
        st.button("Add calculation", icon=":material/add:", key="calc_add", on_click=_add_query)

        # ---- 2. rows and columns
        ui.section("🧱 2 · Rows and columns", "Choose how rows are grouped, which rows to keep, and which quarters to show")
        rc = st.columns(2, gap="large")
        rc[0].multiselect("Rows: group by", levels_here, key="calc_levels", placeholder="Sector",
                          help="In this order, e.g. Sector › Industry Group › companies.")
        top = (ss["calc_levels"] or levels_here[:1])[0]
        top_vals = sorted(view[top].dropna().astype(str).unique()) if top in view.columns else []
        ss["calc_rowfilter"] = [v for v in ss["calc_rowfilter"] if v in top_vals]
        rc[1].multiselect(f"Rows: only these {top.lower()}s", top_vals, key="calc_rowfilter",
                          placeholder=f"All {top.lower()}s")
        st.segmented_control("Columns show", [COL_QUARTERS, COL_CALCS, COL_GROUPS], key="calc_colmode",
                             help="**Quarters**: one table per calculation, a column per quarter.\n\n"
                                  "**Calculations side by side**: one table, a column per calculation "
                                  "(for each quarter you pick).\n\n"
                                  "**Sector / Industry / Group**: pivot style, e.g. rows = Industry Group, "
                                  "columns = Sector.")
        colmode = ss.get("calc_colmode") or COL_QUARTERS
        if colmode == COL_GROUPS:
            free = [lv for lv in levels_here if lv not in (ss["calc_levels"] or levels_here[:1])] or levels_here
            if ss.get("calc_collevel") not in free:
                ss["calc_collevel"] = free[0]
            gc = st.columns(2, gap="large")
            gc[0].selectbox("Columns: split by", free, key="calc_collevel")
            cl = ss["calc_collevel"]
            cl_vals = sorted(view[cl].dropna().astype(str).unique()) if cl in view.columns else []
            ss["calc_colfilter"] = [v for v in (ss.get("calc_colfilter") or []) if v in cl_vals]
            gc[1].multiselect(f"Columns: only these {cl.lower()}s", cl_vals, key="calc_colfilter",
                              placeholder=f"All {cl.lower()}s")
        qc = st.columns([4, 1, 1, 1], vertical_alignment="bottom")
        qc[0].multiselect("Quarters", all_q, key="calc_quarters", placeholder="All quarters",
                          help=None if colmode == COL_QUARTERS else
                          "Tip: pick one quarter (e.g. the latest) to keep the table narrow.")
        qc[1].button("All", key="calc_q_all", width="stretch", on_click=lambda: ss.update(calc_quarters=all_q))
        qc[2].button("Last 4", key="calc_q_4", width="stretch", on_click=lambda: ss.update(calc_quarters=all_q[-4:]))
        qc[3].button("Latest", key="calc_q_1", width="stretch", on_click=lambda: ss.update(calc_quarters=all_q[-1:]))
        st.multiselect("Also show these sheet columns", pivot.formula_columns(numeric), key="calc_extra",
                       placeholder="e.g. Sales Q2 FY26, Market Cap …",
                       help="Added at the end of the table. Amounts are summed per group, margins / growth averaged.")

        with st.expander("More options"):
            o = st.columns(3)
            o[0].selectbox("Group total uses", [AUTO] + pivot.SUMMARIZE, key="calc_s",
                           help="**Auto** = SUM for amounts (Sales, OP, EBIT, PAT) and AVERAGE for margins and "
                                "growth, so a sector's EBIT ÷ PAT = total EBIT ÷ total PAT.")
            o[1].selectbox("Show as", [AUTO, "Percent", "Number"], key="calc_fmt",
                           help="**Auto** = Percent when you divide or use growth, otherwise Number.")
            o[2].number_input("Decimals", 0, 4, key="calc_dec")
            st.toggle("Only count companies that have all the numbers that quarter", key="calc_same")
            st.toggle("Custom formulas: move quarter columns along ('PAT Q1 FY25' becomes PAT of each quarter)",
                      key="calc_roll")

        b = st.columns([1, 1, 4])
        b[0].button("Calculate", icon=":material/calculate:", type="primary", width="stretch", key="calc_go",
                    on_click=_calculate, disabled=not _settings()["queries"])
        b[1].button("Reset", icon=":material/close:", width="stretch", key="calc_clear", on_click=_clear)

    run = ss.get("calc_run")
    if not run or "queries" not in run:
        st.info("Pick what to calculate, then press **Calculate**.")
        return
    if run != _settings():
        st.caption("✎ You changed something — press **Calculate** to update the result.")

    work_view = view
    top = run["levels"][0]
    if run["rowfilter"] and top in view.columns:
        work_view = view[view[top].astype(str).isin(run["rowfilter"])]
    if work_view.empty:
        st.warning("No companies match these filters.")
        return
    show_q = run["quarters"] or all_q
    colmode = run.get("colmode") or COL_QUARTERS
    cols = list(dict.fromkeys([c for c in ui.TREE_COLS if c in view.columns] + numeric))
    base_cols = pivot.formula_columns(numeric)

    # every calculation over the chosen quarters (used by the graphs, and by the Quarters table)
    results = []
    for q in run["queries"]:
        values, extra, error, out_fmt = prepare(work_view, numeric, q["text"], run["summarize"], run["fmt"],
                                                run["dec"], run.get("same", True), run.get("roll", True))
        values = [v for v in values if v["name"] in show_q]
        if error and not values:
            st.markdown(f'<div class="f-err">✕ {q["label"]}: {error}</div>', unsafe_allow_html=True)
        results.append((q, values, extra, out_fmt))
    results = [r for r in results if r[1]]
    if not results:
        st.warning("None of the chosen quarters has all the columns these calculations need.")
        return
    extra_vals = _extra_values(run["extra"], run["dec"])

    if colmode == COL_QUARTERS:
        tabs = st.tabs([f"📊 {q['label']}" for q, *_ in results]) if len(results) > 1 else [st.container()]
        for tab, (q, values, extra, out_fmt) in zip(tabs, results):
            with tab:
                work = pd.concat([work_view[cols], extra], axis=1) if len(extra.columns) else work_view[cols]
                tree = _tree(work, json.dumps(values + extra_vals), tuple(run["levels"]),
                             tuple(base_cols + list(extra.columns)), len(values))
                _show_table(tree, q["label"], run, f"q{q['id']}", len(values))
                graph_tree = _tree(work, json.dumps(values), tuple(run["levels"]),
                                   tuple(base_cols + list(extra.columns)))
                _show_graph(q, graph_tree, out_fmt == "percent", run)
        return

    # ---- one wide table: calculations (and maybe sectors) as columns
    values, extras = [], []
    if colmode == COL_CALCS:
        for q, qvals, extra, _ in results:
            for v in qvals:
                name = q["label"] if len(show_q) == 1 else f"{q['label']} · {v['name']}"
                values.append({**v, "id": f"c{q['id']}_{v['id']}", "name": name})
            extras.append(extra)
        title = "Calculations as columns"
    else:
        cl = run.get("collevel")
        if cl not in work_view.columns:
            st.warning("Pick what to split the columns by.")
            return
        col_vals = run["colfilter"] or list(work_view[cl].dropna().astype(str).value_counts().index)
        n_cols = len(col_vals) * len(results) * len(show_q)
        if n_cols > MAX_COLS:
            st.warning(f"That would be {n_cols:,} columns. Showing the biggest {cl.lower()}s only — pick fewer "
                       f"quarters (e.g. **Latest**) or choose {cl.lower()}s under *Columns: only these*.")
            col_vals = col_vals[:max(1, MAX_COLS // (len(results) * len(show_q)))]
        key_series = work_view[cl].astype(str)
        for i, cv in enumerate(col_vals):
            for q, *_ in results:
                qvals, extra, _, _ = prepare(work_view, numeric, q["text"], run["summarize"], run["fmt"],
                                             run["dec"], run.get("same", True), run.get("roll", True),
                                             row_mask=key_series.eq(cv), tag=f"#{q['id']}·{i} ")
                for v in [v for v in qvals if v["name"] in show_q]:
                    bits = [cv] + ([q["label"]] if len(results) > 1 else []) + ([v["name"]] if len(show_q) > 1 else [])
                    values.append({**v, "id": f"g{i}_{q['id']}_{v['id']}", "name": " · ".join(bits)})
                extras.append(extra)
        title = f"{cl} as columns"
    if not values:
        st.warning("Nothing to show for these choices.")
        return
    extra_df = pd.concat(extras, axis=1) if extras else pd.DataFrame(index=work_view.index)
    extra_df = extra_df.loc[:, ~extra_df.columns.duplicated()]
    work = pd.concat([work_view[cols], extra_df], axis=1)
    tree = _tree(work, json.dumps(values + extra_vals), tuple(run["levels"]),
                 tuple(base_cols + list(extra_df.columns)), len(values))
    _show_table(tree, title, run, "wide", len(values))

    ui.section("📈 Line graphs", "Each calculation over the quarters")
    tabs = st.tabs([f"📊 {q['label']}" for q, *_ in results]) if len(results) > 1 else [st.container()]
    for tab, (q, qvals, extra, out_fmt) in zip(tabs, results):
        with tab:
            w = pd.concat([work_view[cols], extra], axis=1) if len(extra.columns) else work_view[cols]
            gt = _tree(w, json.dumps(qvals), tuple(run["levels"]), tuple(base_cols + list(extra.columns)))
            _show_graph(q, gt, out_fmt == "percent", run, header=False)


def _extra_values(columns: list[str], dec: int) -> list[dict]:
    """Plain sheet columns added to the end of the table: SUM for amounts, AVERAGE for margins / growth."""
    return [pivot.value_defaults({"id": f"x{i}", "name": c, "formula": _quote_eq(c),
                                  "summarize": "AVERAGE" if is_ratio(c) else "SUM",
                                  "format": "number", "decimals": dec}) for i, c in enumerate(columns)]


def _quote_eq(col: str) -> str:
    return "=" + _quote(col)


def _show_table(tree: dict, label: str, run: dict, key: str, n_calc: int) -> None:
    total = tree.get("total") or {}
    st.markdown(f'<div class="f-ok">✓ {label} · {n_calc} column{"s" if n_calc != 1 else ""} · '
                f'{total.get("n", 0):,} companies</div>', unsafe_allow_html=True)
    ui.section("📋 Result table", " › ".join(run["levels"] + [COMPANY])
               + " · highest first on the last column · click a row to open it")
    page = _page(json.dumps(tree), 640, ui.STYLE_VERSION)
    if hasattr(st, "iframe"):
        st.iframe(page, height="content")
    else:
        import streamlit.components.v1 as components
        components.html(page, height=700, scrolling=True)
    frame = pivot.tree_to_frame(tree, True)
    fname = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") or "result"
    st.download_button("Download CSV", frame.to_csv(index=False).encode("utf-8-sig"), f"calculator_{fname}.csv",
                       "text/csv", key=f"calc_csv_{key}", icon=":material/download:")


def _show_graph(q: dict, tree: dict, pct: bool, run: dict, header: bool = True) -> None:
    qid = q["id"]
    how = ("SUM amounts, AVERAGE margins / growth" if run["summarize"] == AUTO else run["summarize"])
    if header:
        ui.section("📈 Line graph", f"{q['label']} · {how} per group · {'%' if pct else 'number'}")
    line_levels = run["levels"] + [COMPANY]
    lv_key, pick_key = f"calc_line_lv_{qid}", f"calc_pick_{qid}"
    if ss.get(lv_key) not in line_levels:
        ss[lv_key] = line_levels[0]
    g1, g2 = st.columns([1.6, 3], vertical_alignment="bottom")
    level = g1.segmented_control("Lines for", line_levels, key=lv_key,
                                 on_change=lambda: ss.update({pick_key: None})) or line_levels[0]
    lines = line_table(tree, level).dropna(how="all")
    if lines.empty:
        st.info("No values to draw.")
        return
    latest = lines.ffill(axis=1).iloc[:, -1]
    options = latest.sort_values(ascending=False, na_position="last").index.tolist()   # highest first
    if not isinstance(ss.get(pick_key), list):
        ss[pick_key] = options[:DEFAULT_LINES]
    ss[pick_key] = [p for p in ss[pick_key] if p in options][:MAX_LINES]
    picks = g2.multiselect(f"{level} lines (up to {MAX_LINES}, highest first)", options, key=pick_key,
                           max_selections=MAX_LINES, placeholder=f"Pick {level.lower()} lines to draw")
    if not picks:
        st.info(f"Pick at least one {level.lower()} to draw.")
        return
    long = lines.loc[picks].reset_index(names="Line").melt(id_vars="Line", var_name="Quarter",
                                                           value_name="Value").dropna()
    fmt = f",.{run['dec']}f"
    unit = "%" if pct else "Value"
    lo, hi = float(long["Value"].min()), float(long["Value"].max())
    pad = (hi - lo) * 0.08 or max(abs(hi) * 0.05, 1.0)          # flat data still gets some room
    domain = [lo - pad, hi + pad]
    quarters_shown = [q for q in lines.columns if q in set(long["Quarter"])]
    base = alt.Chart(long).encode(
        x=alt.X("Quarter:N", sort=quarters_shown, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Value:Q", title=unit, axis=alt.Axis(format=fmt),
                scale=alt.Scale(domain=domain, zero=False, nice=True)),
        color=alt.Color("Line:N", title=None, sort=picks,
                        legend=alt.Legend(orient="bottom", columns=3, labelLimit=280),
                        scale=alt.Scale(range=PALETTE)),
        tooltip=[alt.Tooltip("Line:N", title=level), alt.Tooltip("Quarter:N"),
                 alt.Tooltip("Value:Q", format=fmt, title=unit)])
    hover = alt.selection_point(fields=["Line"], on="pointerover", bind="legend")
    lines_layer = base.mark_line(strokeWidth=2.6, point=alt.OverlayMarkDef(size=55, filled=True)).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0.25))).add_params(hover)
    layers = [lines_layer]
    if lo < 0 < hi:                                              # zero line only when values cross 0
        layers.insert(0, alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#94A3B8", strokeDash=[4, 4])
                      .encode(y="y:Q"))
    chart = alt.layer(*layers).properties(height=420).configure_view(strokeWidth=0).configure_axis(
        labelFont=FONT, titleFont=FONT, labelColor="#475569",
        titleColor="#475569", gridColor="#EEF2F6").configure_legend(labelFont=FONT, labelFontSize=12,
                                                                    labelColor="#0F172A")
    st.altair_chart(chart, width="stretch", theme=None, key=f"calc_chart_{qid}")
    st.caption("Gaps = that quarter doesn't have every column the formula needs (or a value is ÷0).")