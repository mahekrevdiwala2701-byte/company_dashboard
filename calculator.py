"""🧮 Calculator page: one formula box for arithmetic on several columns, worked out for every quarter.

Nothing is shown until you press Calculate. Then you get
  * a table like the main dashboard: Sector › Industry Group › companies (click to open), one column per
    quarter, highest first (sorted on the latest quarter, at every level), Grand Total at the bottom
  * a line graph of the same numbers: pick the sectors / groups / companies to draw

How the formula box works (same rules as the pivot's Calculated field, plus quarter names)
  'Sales', 'PAT', 'OPM' …    a quarter column WITHOUT a quarter = that column for every quarter,
                             e.g. ='PAT' / 'Sales'  →  PAT Q1 FY25 / Sales Q1 FY25, then Q2 FY25, …
  'Sales prev'               the same column one quarter earlier, e.g. =('Sales' / 'Sales prev') - 1
  'Sales Q1 FY25'            a fixed column (the same number on every quarter)
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
KEEP = ["calc_f", "calc_s", "calc_fmt", "calc_dec", "calc_prev", "calc_levels", "calc_run",
        "calc_line_lv", "calc_pick"]
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


def for_quarter(text: str, by_metric: dict, quarters: list, i: int):
    """The formula with every quarter name ('PAT', 'Sales prev') swapped for that quarter's real column.
    Returns (formula text, missing names) — missing = that quarter has no such column."""
    metrics = {_norm(m): m for m in by_metric}
    missing = []

    def swap(m):
        name = m.group(1).replace("''", "'").strip()
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


def uses_quarters(text: str, by_metric: dict) -> bool:
    metrics = {_norm(m) for m in by_metric}
    names = [_norm(n.replace("''", "'")) for n in pivot._REF.findall(text or "")]
    return any(n in metrics or any(n == m + s for m in metrics for s in ("PREV", "PREVIOUS")) for n in names)


# ---------------------------------------------------------------- the maths
def quarter_values(text: str, numeric: list[str], summarize: str, fmt: str, dec: int):
    """One pivot value per quarter (a formula with that quarter's columns).
    Returns (values, first error or None). Quarters missing a column (e.g. 'prev' on the first) are skipped."""
    by_metric, quarters = quarter_info(numeric)
    columns = pivot.formula_columns(numeric)
    values, error = [], None
    for i, fq in enumerate(quarters):
        text_q, missing = for_quarter(text, by_metric, quarters, i)
        if missing:
            continue
        try:
            pivot.compile_formula(text_q, columns, summarize)
        except pivot.FormulaError as e:
            error = error or str(e)
            continue
        values.append(pivot.value_defaults({"id": f"q{fq[0]}{fq[1]}", "name": qname(fq), "formula": text_q,
                                            "summarize": summarize, "format": fmt, "decimals": dec}))
    return values, error


def _layout(values: list[dict], levels: list[str], sort_by: str) -> dict:
    sort = {lv: {"by": sort_by, "dir": "desc"} for lv in levels + [COMPANY]}
    return {"name": "Calculator", "levels": levels, "values": values, "filters": [], "sort": sort,
            "grand_total": True}


@st.cache_data(ttl=600, max_entries=30, show_spinner=False)
def _tree(view: pd.DataFrame, values_json: str, levels: tuple, columns: tuple) -> dict:
    """The result as the dashboard's tree, highest first on the latest quarter that has a value."""
    values = json.loads(values_json)
    tree = pivot.build_tree(view, _layout(values, list(levels), values[-1]["name"]), list(columns))
    total = (tree.get("total") or {}).get("vals") or []
    have = [i for i, v in enumerate(total) if v is not None]
    if have and have[-1] != len(values) - 1:                   # newest quarter is empty: sort on the last full one
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


# ---------------------------------------------------------------- formula box helpers
def _append(token: str) -> None:
    text = ss.get("calc_f", "") or "="
    joiner = "" if text.endswith(("=", "(", " ")) or token in (")", ",") else " "
    ss["calc_f"] = f"{text}{joiner}{token}"


def _insert_pill(key: str, quoted: bool) -> None:
    token = ss.get(key)
    if token:
        if quoted:
            name = token + (" prev" if ss.get("calc_prev") else "")
            token = "'" + name.replace("'", "''") + "'"
        _append(token)
        ss[key] = None


def _insert_fn() -> None:
    _append(FN_INSERT[ss["calc_fn"]])


def _insert_col() -> None:
    col = ss.get("calc_col")
    if col:
        _append("'" + col.replace("'", "''") + "'")
        ss["calc_col"] = None


def _use_example() -> None:
    ex = ss.get("calc_ex")
    if ex:
        ss["calc_f"] = EXAMPLES[ex]
        ss["calc_fmt"] = "Number" if "−" in ex else "Percent"
        ss["calc_ex"] = None


def _clear() -> None:
    ss["calc_f"] = ""
    ss["calc_run"] = None
    ss["calc_pick"] = []


def _settings() -> dict:
    return {"text": (ss.get("calc_f") or "").strip(), "summarize": ss["calc_s"],
            "fmt": "percent" if ss["calc_fmt"] == "Percent" else "number", "dec": int(ss["calc_dec"]),
            "levels": [lv for lv in LEVELS if lv in (ss.get("calc_levels") or [])] or ["Sector"]}


def _calculate() -> None:
    ss["calc_run"] = _settings()
    ss["calc_pick"] = None                                       # fresh lines for the new result


def _keep_values() -> None:
    """Streamlit forgets a widget's value when you visit another page: bring it back."""
    for k in KEEP:
        if k not in ss and f"_keep_{k}" in ss:
            ss[k] = ss[f"_keep_{k}"]


def _remember() -> None:
    for k in KEEP:
        if k in ss:
            ss[f"_keep_{k}"] = ss[k]


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
    ss.setdefault("calc_f", "")
    ss.setdefault("calc_s", "SUM")
    ss.setdefault("calc_fmt", "Percent")
    ss.setdefault("calc_dec", 2)
    ss.setdefault("calc_prev", False)
    ss.setdefault("calc_levels", ["Sector", "Industry Group"])
    ss.setdefault("calc_run", None)

    if not quarters:
        st.warning("No quarter columns found (like 'Sales Q1 FY25'), so there is nothing to work out per quarter.")
        return

    # ---- the formula box
    with st.container(key="calcbox"):
        ui.section("🧮 Formula", f"Maths on several columns, worked out for every quarter "
                                 f"{qname(quarters[0])} → {qname(quarters[-1])}")
        left, right = st.columns([3, 2], gap="large")
        with left:
            st.text_area("Formula", key="calc_f", height=96,
                         placeholder="e.g. ='PAT' / 'Sales'   or   =('Sales' / 'Sales prev') - 1")
            st.pills("Operators", OPERATORS, key="calc_op", label_visibility="collapsed",
                     on_change=_insert_pill, args=("calc_op", False))
            f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
            fn = f1.selectbox("Function", list(FN_HELP), key="calc_fn")
            f2.button("Insert", key="calc_fnins", on_click=_insert_fn, width="stretch")
            st.caption(FN_HELP[fn])
        with right:
            st.pills("Quarter columns (click to add)", [_label(m) for m in by_metric], key="calc_q",
                     on_change=_insert_pill, args=("calc_q", True))
            st.toggle("Add them as the previous quarter ('Sales prev')", key="calc_prev")
            st.selectbox("Any other column (fixed, same on every quarter)", pivot.formula_columns(numeric),
                         key="calc_col", index=None, placeholder="Search a column…", on_change=_insert_col)
            st.selectbox("Or start from an example", list(EXAMPLES), key="calc_ex", index=None,
                         placeholder="Pick an example…", on_change=_use_example)

        c = st.columns([1.15, 0.95, 0.6, 2.1, 0.9, 0.7], vertical_alignment="bottom")
        c[0].selectbox("Summarize each group by", pivot.SUMMARIZE, key="calc_s",
                       help="For a sector / group row, each column in the formula is first summarised this "
                            "way for the group, then the formula runs (like the pivot). SUM of PAT ÷ SUM of Sales "
                            "= the group's margin. For one company it makes no difference.")
        c[1].selectbox("Show as", ["Percent", "Number"], key="calc_fmt",
                       help="Percent multiplies by 100 and adds %, e.g. 0.12 → 12%.")
        c[2].number_input("Decimals", 0, 4, key="calc_dec")
        c[3].multiselect("Rows", LEVELS, key="calc_levels", placeholder="Sector",
                         help="Like the main dashboard: Sector › Industry Group › companies.")
        c[4].button("Calculate", icon=":material/calculate:", type="primary", width="stretch",
                    key="calc_go", on_click=_calculate, disabled=(ss.get("calc_f") or "").strip() in ("", "="))
        c[5].button("Clear", icon=":material/close:", width="stretch", key="calc_clear", on_click=_clear)

    run = ss.get("calc_run")
    if not run:
        st.info("Type a formula (or click columns, operators or an example), then press **Calculate**.")
        return
    if run != _settings():
        st.caption("✎ You changed the formula or options — press **Calculate** to update the result.")
    if view.empty:
        st.warning("No companies match these filters.")
        return

    # ---- work it out
    values, error = quarter_values(run["text"], numeric, run["summarize"], run["fmt"], run["dec"])
    if not values:
        msg = error or "No quarter has all the columns this formula needs."
        st.markdown(f'<div class="f-err">✕ {msg}</div>', unsafe_allow_html=True)
        return
    if not uses_quarters(run["text"], by_metric):
        st.info("This formula doesn't use a quarter column like 'Sales' or 'PAT', so it is the same on every "
                "quarter. Use a quarter name without the quarter (e.g. 'PAT') to see it change over time.")
    cols = list(dict.fromkeys([c for c in ui.TREE_COLS if c in view.columns] + numeric))
    with st.spinner("Calculating…"):
        tree = _tree(view[cols], json.dumps(values), tuple(run["levels"]), tuple(pivot.formula_columns(numeric)))
    pct = run["fmt"] == "percent"
    st.markdown(f'<div class="f-ok">✓ {run["text"]} · {len(values)} quarter{"s" if len(values) != 1 else ""} · '
                f'{(tree.get("total") or {}).get("n", len(view)):,} companies</div>', unsafe_allow_html=True)

    # ---- the table, like the main dashboard
    ui.section("📋 Result table", " › ".join(run["levels"] + [COMPANY])
               + " · highest first on the latest quarter · click a row to open it")
    page = _page(json.dumps(tree), 640, ui.STYLE_VERSION)
    if hasattr(st, "iframe"):
        st.iframe(page, height="content")
    else:
        import streamlit.components.v1 as components
        components.html(page, height=700, scrolling=True)
    frame = pivot.tree_to_frame(tree, True)
    st.download_button("Download CSV", frame.to_csv(index=False).encode("utf-8-sig"), "calculator_result.csv",
                       "text/csv", key="calc_csv", icon=":material/download:")

    # ---- the line graph
    ui.section("📈 Line graph", run["text"] + (f" · {run['summarize']} per group" if run["levels"] else ""))
    line_levels = run["levels"] + [COMPANY]
    if ss.get("calc_line_lv") not in line_levels:
        ss["calc_line_lv"] = line_levels[0]
    g1, g2 = st.columns([1.6, 3], vertical_alignment="bottom")
    level = g1.segmented_control("Lines for", line_levels, key="calc_line_lv",
                                 on_change=lambda: ss.update(calc_pick=None)) or line_levels[0]
    lines = line_table(tree, level).dropna(how="all")
    if lines.empty:
        st.info("No values to draw.")
        return
    latest = lines.ffill(axis=1).iloc[:, -1]
    options = latest.sort_values(ascending=False, na_position="last").index.tolist()   # highest first
    if not isinstance(ss.get("calc_pick"), list):
        ss["calc_pick"] = options[:DEFAULT_LINES]
    ss["calc_pick"] = [p for p in ss["calc_pick"] if p in options][:MAX_LINES]
    picks = g2.multiselect(f"{level} lines (up to {MAX_LINES}, highest first)", options, key="calc_pick",
                           max_selections=MAX_LINES, placeholder=f"Pick {level.lower()} lines to draw")
    if not picks:
        st.info(f"Pick at least one {level.lower()} to draw.")
        return
    long = lines.loc[picks].reset_index(names="Line").melt(id_vars="Line", var_name="Quarter",
                                                           value_name="Value").dropna()
    fmt = f",.{run['dec']}f"
    unit = "%" if pct else "Value"
    base = alt.Chart(long).encode(
        x=alt.X("Quarter:N", sort=list(lines.columns), title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Value:Q", title=unit, axis=alt.Axis(format=fmt)),
        color=alt.Color("Line:N", title=None, sort=picks,
                        legend=alt.Legend(orient="bottom", columns=3, labelLimit=280),
                        scale=alt.Scale(range=PALETTE)),
        tooltip=[alt.Tooltip("Line:N", title=level), alt.Tooltip("Quarter:N"),
                 alt.Tooltip("Value:Q", format=fmt, title=unit)])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#94A3B8", strokeDash=[4, 4]).encode(y="y:Q")
    chart = (zero + base.mark_line(strokeWidth=2.6, point=alt.OverlayMarkDef(size=55, filled=True))
             ).properties(height=420).configure_view(strokeWidth=0).configure_axis(
        labelFont=FONT, titleFont=FONT, labelColor="#475569",
        titleColor="#475569", gridColor="#EEF2F6").configure_legend(labelFont=FONT, labelFontSize=12,
                                                                    labelColor="#0F172A")
    st.altair_chart(chart, width="stretch", theme=None)
    st.caption("Gaps = that quarter doesn't have every column the formula needs (or a value is ÷0).")