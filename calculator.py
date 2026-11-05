"""🧮 Calculator page: one formula box for arithmetic on several columns, worked out for every quarter
and drawn as a line graph (Q1 FY25 → latest quarter).

How the formula box works (same rules as the pivot's Calculated field, plus quarter names)
  'Sales', 'PAT', 'OPM' …    a quarter column WITHOUT a quarter = that column for every quarter,
                             e.g. ='PAT' / 'Sales'  →  PAT Q1 FY25 / Sales Q1 FY25, then Q2 FY25, …
  'Sales prev'               the same column one quarter earlier, e.g. =('Sales' / 'Sales prev') - 1
  'Sales Q1 FY25'            a fixed column (the same number on every quarter)
  + − × ÷ ^ %, brackets, and every function in the pivot's Function list (ROUND, IF, AVERAGE …)

Lines: one line for all filtered companies together, or one per Sector / Industry / Industry Group /
Sub group / company. A group's value is worked out like the pivot: each column is first summarised
for the group (SUM by default), then the formula runs, e.g. SUM of PAT ÷ SUM of Sales.
"""

import re

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

import pivot
import ui
from data import LEVELS

ss = st.session_state
ALL = "All filtered companies"
COMPANY = "Company"
GROUP_BY = [ALL] + LEVELS + [COMPANY]
OPERATORS = ["+", "−", "×", "÷", "^", "(", ")", ","]
FN_HELP = {name: helptext for name, _, helptext in pivot.FUNCTIONS}
FN_INSERT = {name: ins for name, ins, _ in pivot.FUNCTIONS}
MAX_LINES = 12
KEEP = ["calc_f", "calc_by", "calc_pick", "calc_s", "calc_fmt", "calc_dec", "calc_prev"]
EXAMPLES = {
    "PAT margin": "='PAT' / 'Sales'",
    "Sales growth vs previous quarter": "=('Sales' / 'Sales prev') - 1",
    "PAT growth vs previous quarter": "=('PAT' / 'PAT prev') - 1",
    "Operating profit share of EBIT": "='OP' / 'EBIT'",
    "Sales − OP (costs)": "='Sales' - 'OP'",
}


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
def _groups(view: pd.DataFrame, by: str) -> pd.Series:
    """The line each company belongs to."""
    if by == ALL:
        return pd.Series(ALL, index=view.index)
    if by == COMPANY:
        name = view["Name"].astype(str) if "Name" in view.columns else pd.Series("", index=view.index)
        code = view.get("NSE Code", pd.Series("", index=view.index)).astype(str)
        code = code.where(code.str.strip() != "", view.get("BSE Code", pd.Series("", index=view.index)).astype(str))
        return (name + np.where(code.str.strip() != "", " (" + code + ")", "")).str.strip()
    return view[by].astype(str).replace("", pivot.UNMAPPED)


def calculate(view: pd.DataFrame, numeric: list[str], text: str, summarize: str, by: str):
    """Result per line and quarter: DataFrame (index = line, columns = 'Q1 FY25' …), first error or None."""
    by_metric, quarters = quarter_info(numeric)
    columns = pivot.formula_columns(numeric)
    groups = _groups(view, by)
    lines = groups.drop_duplicates().tolist() if by != COMPANY else groups.tolist()
    table = pd.DataFrame(index=pd.Index(lines, name=by if by != ALL else "Line"),
                         columns=[qname(q) for q in quarters], dtype=float)
    first_error = None
    for i, fq in enumerate(quarters):
        text_q, missing = for_quarter(text, by_metric, quarters, i)
        if missing:
            continue                                             # this quarter has no such column: gap
        try:
            f = pivot.compile_formula(text_q, columns, summarize)
        except pivot.FormulaError as e:
            first_error = first_error or str(e)
            continue
        data = pivot._prep(view, {c for c, _ in f.cols.values()})
        if by == COMPANY:
            res = pivot._run(f, pivot._row_env(data, f.cols))
            res = np.broadcast_to(res, len(view))
            table[qname(fq)] = pd.Series(res, index=groups.values).groupby(level=0).first().reindex(table.index)
        else:
            gb = data.groupby(groups.values, sort=False)
            sizes = gb.size()
            res = pivot._run(f, pivot._group_env(data, gb, f.cols, sizes.index, {}))
            table[qname(fq)] = pd.Series(np.broadcast_to(res, len(sizes)), index=sizes.index).reindex(table.index)
    return table, first_error


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
    ctx = ss["ctx"]
    view, numeric = ctx["view"], ctx["numeric"]
    by_metric, quarters = quarter_info(numeric)
    _keep_values()
    ss.setdefault("calc_f", EXAMPLES["PAT margin"])
    ss.setdefault("calc_by", "Sector")
    ss.setdefault("calc_s", "SUM")
    ss.setdefault("calc_fmt", "Percent")
    ss.setdefault("calc_dec", 2)
    ss.setdefault("calc_prev", False)

    if view.empty:
        st.warning("No companies match these filters.")
        return
    if not quarters:
        st.warning("No quarter columns found (like 'Sales Q1 FY25'), so there is nothing to draw over time.")
        return

    metric_names = [_label(m) for m in by_metric]
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
            st.pills("Quarter columns (click to add)", metric_names, key="calc_q",
                     on_change=_insert_pill, args=("calc_q", True))
            st.toggle("Add them as the previous quarter ('Sales prev')", key="calc_prev")
            st.selectbox("Any other column (fixed, same on every quarter)", pivot.formula_columns(numeric),
                         key="calc_col", index=None, placeholder="Search a column…", on_change=_insert_col)
            st.selectbox("Or start from an example", list(EXAMPLES), key="calc_ex", index=None,
                         placeholder="Pick an example…", on_change=_use_example)

        c1, c2, c3, c4 = st.columns([1.3, 1.1, 0.7, 2.6], vertical_alignment="bottom")
        c1.selectbox("Summarize each group by", pivot.SUMMARIZE, key="calc_s",
                     help="For a sector / group line, each column in the formula is first summarised this "
                          "way for the group, then the formula runs (like the pivot). SUM of PAT ÷ SUM of Sales "
                          "= the group's margin. For one company it makes no difference.")
        c2.selectbox("Show as", ["Percent", "Number"], key="calc_fmt",
                     help="Percent multiplies by 100 and adds %, e.g. 0.12 → 12%.")
        c3.number_input("Decimals", 0, 4, key="calc_dec")
        by = c4.segmented_control("One line for", GROUP_BY, key="calc_by") or "Sector"

    text = ss["calc_f"]
    if text.strip() in ("", "="):
        st.info("Type a formula above, click columns and operators, or pick an example.")
        _remember()
        return

    with st.spinner("Calculating…"):
        table, error = calculate(view, numeric, text, ss["calc_s"], by)
    filled = table.dropna(how="all")
    if error and filled.empty:
        st.markdown(f'<div class="f-err">✕ {error}</div>', unsafe_allow_html=True)
        _remember()
        return
    if not uses_quarters(text, by_metric):
        st.info("This formula doesn't use a quarter column like 'Sales' or 'PAT', so it is the same on every "
                "quarter. Use a quarter name without the quarter (e.g. 'PAT') to see it change over time.")
    if filled.empty:
        st.markdown('<div class="f-err">✕ No quarter has all the columns this formula needs.</div>',
                    unsafe_allow_html=True)
        _remember()
        return
    n_q = int(table.notna().any().sum())
    st.markdown(f'<div class="f-ok">✓ Formula works · {len(filled):,} line{"s" if len(filled) != 1 else ""} · '
                f'{n_q} of {len(table.columns)} quarters have a value</div>', unsafe_allow_html=True)

    # ---- which lines to draw
    pct = ss["calc_fmt"] == "Percent"
    dec = int(ss["calc_dec"])
    shown = filled
    if by != ALL:
        latest = filled.ffill(axis=1).iloc[:, -1]
        default = latest.sort_values(ascending=False).index[:6].tolist()       # 6 highest by latest value
        options = filled.index.tolist()
        if not isinstance(ss.get("calc_pick"), list) or ss.get("_calc_pick_for") != (by, text):
            ss["calc_pick"] = default
            ss["_calc_pick_for"] = (by, text)
        ss["calc_pick"] = [p for p in ss["calc_pick"] if p in options][:MAX_LINES]
        picks = st.multiselect(f"{by} lines on the graph (up to {MAX_LINES})", options, key="calc_pick",
                               max_selections=MAX_LINES, placeholder=f"Pick {by.lower()}s to draw")
        shown = filled.loc[picks] if picks else filled.iloc[:0]
        st.caption(f"Starts with the 6 highest on the latest quarter · {len(options):,} to choose from.")

    # ---- the line graph
    if shown.empty:
        st.info(f"Pick at least one {by.lower()} to draw.")
    else:
        long = (shown * (100 if pct else 1)).reset_index(names="Line").melt(
            id_vars="Line", var_name="Quarter", value_name="Value").dropna()
        order = list(table.columns)
        fmt = f",.{dec}f"
        base = alt.Chart(long).encode(
            x=alt.X("Quarter:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Value:Q", title="%" if pct else "Value", axis=alt.Axis(format=fmt)),
            color=alt.Color("Line:N", title=None, legend=alt.Legend(orient="bottom", columns=3, labelLimit=260),
                            scale=alt.Scale(range=["#0F766E", "#0284C7", "#D97706", "#E11D48", "#65A30D",
                                                   "#7C3AED", "#0891B2", "#EA580C", "#DB2777", "#16A34A",
                                                   "#CA8A04", "#2563EB"])),
            tooltip=[alt.Tooltip("Line:N", title=by), alt.Tooltip("Quarter:N"),
                     alt.Tooltip("Value:Q", format=fmt, title="%" if pct else "Value")])
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#94A3B8", strokeDash=[4, 4]).encode(y="y:Q")
        chart = (zero + base.mark_line(strokeWidth=2.6, point=alt.OverlayMarkDef(size=55, filled=True))
                 ).properties(height=420).configure_view(strokeWidth=0).configure_axis(
            labelFont="Plus Jakarta Sans", titleFont="Plus Jakarta Sans", gridColor="#EEF2F6")
        ui.section("📈 Result over time", f"{text}  ·  {ss['calc_s']} per group" if by not in (ALL, COMPANY)
                   else text)
        st.altair_chart(chart, width="stretch")
        st.caption("Gaps = that quarter doesn't have every column the formula needs (or a value is ÷0).")

    # ---- the result table + CSV
    ui.section("📋 Result table", "Every line and every quarter · newest quarter on the right")
    out = (filled * (100 if pct else 1)).round(dec + 2)
    if by != ALL:
        out = out.loc[[i for i in (shown.index.tolist() + [x for x in filled.index if x not in shown.index])]]
    show_all = by == ALL or st.toggle("Show every line in the table (not only the ones on the graph)",
                                      key="calc_tbl_all")
    table_view = out if show_all else out.loc[shown.index]
    lim = ui.color_limit(table_view.stack()) if len(table_view) else 0
    sty = table_view.style.format(f"{{:,.{dec}f}}" + ("%" if pct else ""), na_rep="–")
    if lim:
        sty = sty.map(lambda v: ui.cell_bg(v, lim))
    st.dataframe(sty, width="stretch", height=min(520, 40 + 35 * max(1, len(table_view))))
    st.download_button("⬇ Download CSV", out.to_csv().encode("utf-8-sig"), "calculator_result.csv", "text/csv",
                       key="calc_csv")
    _remember()