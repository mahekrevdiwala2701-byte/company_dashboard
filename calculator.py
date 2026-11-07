"""🧮 Calculator page: a calculated field, worked out for EVERY quarter — one column per quarter.

Same editor as the dashboard's Calculated field (Quick maths, formula box, operators, Function list,
Sheet columns · Pivot columns, Summarize by, Format, Decimals). Write the formula for one quarter, e.g.
    ='EBIT Q1 FY25' / 'PAT Q1 FY25'
and the table shows it for Q1 FY25, Q2 FY25, … the latest quarter (the quarter columns move along).
Below the table: a line graph of the same numbers (pick sectors / groups / companies).

Formula rules (same as the dashboard, plus quarters)
  'Sales Q1 FY25'      a quarter column: moved along to every quarter, relative to the latest quarter
                       in the formula, so ='Sales Q2 FY25' / 'Sales Q1 FY25' - 1 = growth vs previous quarter
  'Sales' / 'Sales prev'   the column of each quarter / of the quarter before (shortcut)
  'Market Cap'         a column without a quarter: the same number for every quarter
  [Pivot column]       another calculated field of this page, e.g. =[PAT margin] * 100
  + − × ÷ ^ %, brackets, and every function in the Function list (ROUND, IF, AVERAGE …)

A sector / group value is worked out like the pivot: each column is first summarised for the group
(SUM, or Auto = SUM for amounts and AVERAGE for margins / growth), then the formula runs.
"""

import html
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
AUTO = "Auto"
OPERATORS = ["+", "−", "×", "÷", "^", "%", "(", ")", ",", ">", "<", ">=", "<=", "=", "<>"]
FN_HELP = {name: helptext for name, _, helptext in pivot.FUNCTIONS}
FN_INSERT = {name: ins for name, ins, _ in pivot.FUNCTIONS}
SUMMARIZE_CALC = [AUTO] + pivot.SUMMARIZE + [pivot.CUSTOM]
FORMATS = {AUTO: "Auto", "percent": "Percent", "number": "Number"}
MAX_LINES = 12
DEFAULT_LINES = 5
FONT = "Plus Jakarta Sans, Segoe UI, Arial, sans-serif"
KEEP = ["calc_levels", "calc_qids", "calc_next", "calc_cmp_lv", "calc_cmp_calcs", "calc_view"]
KEEP_PREFIX = ("cq_", "calc_pick_", "calc_line_lv_", "calc_cmp_pick_")   # per-calculation widgets
GRAND = "Grand total"
CUSTOM = "✏️ Custom formula"
# Old calculator (A / operation / B boxes) — only used to turn old calculations into formulas
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
# {X} = column X of the first quarter, {X+} = of the second quarter (the formula then moves along)
EXAMPLES = {
    "EBIT ÷ PAT": "={EBIT} / {PAT}",
    "PAT margin": "={PAT} / {SALES}",
    "Sales growth vs previous quarter": "=({SALES+} / {SALES}) - 1",
    "PAT growth vs previous quarter": "=({PAT+} / {PAT}) - 1",
    "Operating profit share of EBIT": "={OP} / {EBIT}",
    "Sales − OP (costs)": "={SALES} - {OP}",
}


def example_formula(template: str, numeric: list[str]) -> str | None:
    """'={PAT} / {SALES}' → "='PAT Q1 FY25' / 'Sales Q1 FY25'" with this sheet's real column names."""
    by_metric, quarters = quarter_info(numeric)
    missing = []

    def sub(m):
        cols = by_metric.get(m.group(1), {})
        i = 1 if m.group(2) else 0
        col = cols.get(quarters[i]) if len(quarters) > i else None
        if col is None:
            missing.append(m.group(1))
            return m.group(0)
        return "'" + col.replace("'", "''") + "'"

    out = re.sub(r"\{([A-Z ]+?)(\+)?\}", sub, template)
    return None if missing else out
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


def _qids() -> list[int]:
    return list(ss.get("calc_qids") or [])


def _add_query(name: str = "", formula: str = "", summarize: str = AUTO, fmt: str = AUTO, dec: int = 2) -> int:
    qid = ss.get("calc_next", 1)
    ss["calc_next"] = qid + 1
    ss[_k(qid, "name")] = name
    ss[_k(qid, "f")] = formula
    ss[_k(qid, "s")] = summarize
    ss[_k(qid, "fmt")] = fmt
    ss[_k(qid, "dec")] = int(dec)
    ss["calc_qids"] = _qids() + [qid]
    return qid


def _remove_query(qid: int) -> None:
    ss["calc_qids"] = [q for q in _qids() if q != qid]
    for k in [k for k in ss if str(k).startswith(f"cq_{qid}_") or k in (f"calc_pick_{qid}", f"calc_line_lv_{qid}")]:
        del ss[k]


def _unique_name(name: str, skip: int | None = None) -> str:
    taken = {_query_label(q).lower() for q in _qids() if q != skip}
    out, n = name, 2
    while out.lower() in taken:
        out, n = f"{name} ({n})", n + 1
    return out


def _duplicate(qid: int) -> None:
    new = _add_query(_unique_name(f"{_query_label(qid)} copy"), ss.get(_k(qid, "f")) or "",
                     ss.get(_k(qid, "s"), AUTO), ss.get(_k(qid, "fmt"), AUTO), ss.get(_k(qid, "dec"), 2))
    ids = [q for q in _qids() if q != new]
    ids.insert(ids.index(qid) + 1, new)                      # right below the one copied
    ss["calc_qids"] = ids


def _move_query(qid: int, step: int) -> None:
    ids = _qids()
    i = ids.index(qid)
    if 0 <= i + step < len(ids):
        ids[i], ids[i + step] = ids[i + step], ids[i]
    ss["calc_qids"] = ids


def _migrate(qid: int) -> None:
    """Calculations made with the old Column / Operation / Second column boxes → a formula + name,
    and the old page-wide 'Group total uses / Show as / Decimals' → this calculation's own settings."""
    op = ss.get(_k(qid, "op"))
    if op in SIMPLE_OPS and op != CUSTOM and not (ss.get(_k(qid, "f")) or "").strip():
        a, b = ss.get(_k(qid, "a")), ss.get(_k(qid, "b"))
        pattern, needs_b, label = SIMPLE_OPS[op]
        if a and (b or not needs_b):
            ss[_k(qid, "f")] = pattern.format(a=a.replace("'", "''"), b=(b or "").replace("'", "''"))
            if not (ss.get(_k(qid, "name")) or "").strip():
                ss[_k(qid, "name")] = label.format(A=a, B=b or "")
    for part in ("a", "op", "b"):
        ss.pop(_k(qid, part), None)
        ss.pop(f"_keep_{_k(qid, part)}", None)
    old_fmt = {"Percent": "percent", "Number": "number"}.get(ss.get("calc_fmt"), AUTO)
    ss.setdefault(_k(qid, "s"), ss.get("calc_s", AUTO))
    ss.setdefault(_k(qid, "fmt"), old_fmt)
    ss.setdefault(_k(qid, "dec"), int(ss.get("calc_dec", 2)))
    ss.setdefault(_k(qid, "name"), "")
    ss.setdefault(_k(qid, "f"), "")


def _raw(qid: int) -> str:
    t = (ss.get(_k(qid, "f")) or "").strip()
    return "" if t in ("", "=") else (t if t.startswith("=") else "=" + t)


def _query_label(qid: int) -> str:
    return (ss.get(_k(qid, "name")) or "").strip() or _raw(qid).lstrip("=") or f"Calculation {qid}"


def _calc_formulas(skip: int | None = None) -> dict[str, str]:
    """{calculation name (lower case): its formula} — what [Name] in a formula points at."""
    return {_query_label(q).lower(): _raw(q) for q in _qids() if q != skip and _raw(q)}


def expand(text: str, formulas: dict[str, str], seen: tuple = ()) -> str:
    """[Other calculation] → (its formula), so one calculation can build on another."""
    def sub(m):
        name = m.group(1).strip()
        key = name.lower()
        if key in seen:
            raise pivot.FormulaError(f"[{name}] uses itself (a loop) — change one of the formulas.")
        if key not in formulas:
            raise pivot.FormulaError(f"No calculation called [{name}]. Pick it from the Calculations tab.")
        return "(" + expand(formulas[key].lstrip("=").strip(), formulas, seen + (key,)) + ")"

    return pivot._VREF.sub(sub, text or "")


def _rename_refs(old: str, new: str) -> None:
    """A calculation was renamed: keep [Old name] in other formulas pointing at it."""
    pattern = re.compile(r"\[\s*" + re.escape(old) + r"\s*\]", re.I)
    for q in _qids():
        if ss.get(_k(q, "f")):
            ss[_k(q, "f")] = pattern.sub(lambda _: f"[{new}]", ss[_k(q, "f")])


def _default_query(numeric: list[str]) -> None:
    for name in ("EBIT ÷ PAT", "PAT margin"):
        f = example_formula(EXAMPLES[name], numeric)
        if f:
            _add_query(name, f)
            return
    cols = ss.get("_calc_cols") or []
    if cols:
        _add_query(cols[0], _quote_eq(cols[0]))


def _add_example(name: str, formula: str) -> None:
    _add_query(_unique_name(name), formula)


def _queries() -> list[dict]:
    """Every calculation with its formula expanded ([Other] → its formula) and its own settings."""
    out = []
    for qid in _qids():
        raw = _raw(qid)
        if not raw:
            continue
        label = _query_label(qid)
        q = {"id": qid, "raw": raw, "label": label, "summarize": ss.get(_k(qid, "s"), AUTO),
             "fmt": ss.get(_k(qid, "fmt"), AUTO), "dec": int(ss.get(_k(qid, "dec"), 2))}
        try:
            q["text"] = expand(raw, _calc_formulas(qid), (label.lower(),))
        except pivot.FormulaError as e:
            q["text"], q["error"] = "", str(e)
        out.append(q)
    return out


# ---------------------------------------------------------------- calculated field editor (like the dashboard)
def _ref(kind: str, name: str) -> str:
    return f"[{name}]" if kind == "calc" else _quote(name)


def _append(fkey: str, token: str) -> None:
    text = ss.get(fkey, "") or "="
    joiner = "" if text.endswith(("=", "(", " ")) or token in (")", ",") else " "
    ss[fkey] = f"{text}{joiner}{token}"


def _insert(fkey: str, pkey: str, kind: str) -> None:
    """Clicked an operator, a column or a calculation → add it to the end of the formula."""
    token = ss.get(pkey)
    if token:
        _append(fkey, token if kind == "op" else _ref(kind, token))
        ss[pkey] = None


def _insert_fn(fkey: str, skey: str) -> None:
    _append(fkey, FN_INSERT[ss[skey]])


def _quick(k: str) -> None:
    """Quick maths: A ⊕ B → a ready formula (replaces what is in the box)."""
    a, op, b = ss[f"{k}_qa"], ss[f"{k}_qop"], ss[f"{k}_qb"]
    if not a or not b:
        return
    template, fmt = pivot.QUICK_OPS[op]
    rb = f"{ss[f'{k}_qn']:g}" if b[0] == "num" else _ref(*b)
    ss[f"{k}_f"] = "=" + template.format(a=_ref(*a), b=rb)
    other = f"{ss[f'{k}_qn']:g}" if b[0] == "num" else b[1]
    if ss.get(f"{k}_auto_name", True):
        ss[f"{k}_name"] = op.replace("A", a[1], 1).replace("B", other, 1)[:80]
    if fmt:
        ss[f"{k}_fmt"] = fmt


def _name_typed(k: str) -> None:
    ss[f"{k}_auto_name"] = False                             # user typed a name: stop suggesting one


def _matches(query: str, name: str) -> bool:
    """Every word must appear; commas mean 'either', e.g. "pat q2, sales q2"."""
    q = (query or "").strip().lower()
    if not q:
        return True
    n = name.lower()
    return any(all(w in n for w in alt_.split()) for alt_ in q.split(",") if alt_.strip())


def check(raw: str, view: pd.DataFrame, numeric: list[str], summarize: str, formulas: dict,
          self_name: str, roll: bool):
    """Live check for the formula box → (error or None, info for the ✓ line)."""
    if raw.strip() in ("", "="):
        return "Type a formula, or use Quick maths / the buttons and lists.", None
    try:
        text = expand(raw, formulas, (self_name.strip().lower(),))
    except pivot.FormulaError as e:
        return str(e), None
    by_metric, quarters = quarter_info(numeric)
    columns = pivot.formula_columns(numeric)
    lookup = {c.lower(): c for c in columns}
    ok = [i for i in range(len(quarters)) if not for_quarter(text, by_metric, quarters, i, roll)[1]]
    if not ok:
        return "No quarter has every column this formula needs.", None
    i = ok[-1]
    reads = for_quarter(text, by_metric, quarters, i, roll)[0]
    text_q = _auto_summary(reads, lookup) if summarize == AUTO else reads
    err, sample = pivot.check_formula(text_q, view, columns, "SUM" if summarize == AUTO else summarize)
    if err:
        return err, None
    return None, {"quarter": qname(quarters[i]), "reads": reads, "n_ok": len(ok), "n_all": len(quarters),
                  "sample": sample, "moves": uses_quarters(text, by_metric, quarters, roll),
                  "fmt": auto_format(text, set())}


@st.dialog("Calculated field", width="large")
def calc_dialog(view: pd.DataFrame, numeric: list[str], qid: int | None = None) -> None:
    sheet = pivot.formula_columns(numeric)
    others = {o: _query_label(o) for o in _qids() if o != qid and _raw(o)}
    formulas = _calc_formulas(qid)
    k = f"cfd_{qid or 'new'}_{ss.get('calc_dlg', 0)}"
    if f"{k}_f" not in ss:                                    # first open: fill the boxes
        ss[f"{k}_f"] = _raw(qid) or "=" if qid else "="
        ss[f"{k}_name"] = _query_label(qid) if qid else _unique_name(f"Calculation {len(_qids()) + 1}")
        ss[f"{k}_auto_name"] = qid is None
        ss[f"{k}_s"] = ss.get(_k(qid, "s"), AUTO) if qid else AUTO
        ss[f"{k}_fmt"] = ss.get(_k(qid, "fmt"), AUTO) if qid else AUTO
        ss[f"{k}_dec"] = int(ss.get(_k(qid, "dec"), 2)) if qid else 2

    st.caption("Write it for one quarter, e.g. ='EBIT Q1 FY25' / 'PAT Q1 FY25' — the table works it out for "
               "every quarter, one column per quarter. [Brackets] = another calculated field of this page.")

    # ---- quick builder
    with st.expander("Quick maths: A ⊕ B", expanded=qid is None, icon=":material/calculate:"):
        refs = [("calc", n) for n in others.values()] + [("col", c) for c in sheet]
        label = (lambda o: "A number…" if o[0] == "num" else f"[{o[1]}]" if o[0] == "calc" else o[1])
        q1, q2, q3, q4 = st.columns([2.2, 1.4, 2.2, 0.9], vertical_alignment="bottom")
        q1.selectbox("A", refs, key=f"{k}_qa", format_func=label, index=None, placeholder="Pick a column")
        q2.selectbox("Operation", list(pivot.QUICK_OPS), key=f"{k}_qop")
        q3.selectbox("B", [("num", "")] + refs, key=f"{k}_qb", format_func=label, index=None,
                     placeholder="Pick a column or a number")
        if (ss.get(f"{k}_qb") or ("",))[0] == "num":
            q4.number_input("Number", value=100.0, key=f"{k}_qn", format="%g")
        else:
            ss.setdefault(f"{k}_qn", 100.0)
        st.button("Use this formula", icon=":material/arrow_downward:", on_click=_quick, args=(k,),
                  disabled=not (ss.get(f"{k}_qa") and ss.get(f"{k}_qb")), key=f"{k}_quse")
        st.caption("[Brackets] = another calculated field of this page · plain = a sheet column.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        name = st.text_input("Calculated field name", key=f"{k}_name", on_change=_name_typed, args=(k,))
        formula = st.text_area("Formula", key=f"{k}_f", height=110, placeholder="='EBIT Q1 FY25' / 'PAT Q1 FY25'")
        st.pills("Operators", OPERATORS, key=f"{k}_op", label_visibility="collapsed",
                 on_change=_insert, args=(f"{k}_f", f"{k}_op", "op"))
        f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
        fn = f1.selectbox("Function", list(FN_HELP), key=f"{k}_fn",
                          format_func=lambda n: f"{n} — {FN_HELP[n].split('→')[-1].strip()}" if "→" in FN_HELP[n] else n)
        f2.button("Insert", key=f"{k}_fnins", on_click=_insert_fn, args=(f"{k}_f", f"{k}_fn"), width="stretch")
        st.caption(FN_HELP[fn])
        c1, c2, c3 = st.columns([1.4, 1, 0.8])
        summarize = c1.selectbox("Summarize by", SUMMARIZE_CALC, key=f"{k}_s",
                                 help="How a sector / group total is made before the formula runs (like the "
                                      "pivot). **Auto** = SUM for amounts (Sales, OP, EBIT, PAT) and AVERAGE for "
                                      "margins and growth, so a sector's PAT ÷ Sales = total PAT ÷ total Sales. "
                                      "CUSTOM: write summaries yourself, e.g. =SUM('PAT') / COUNTA('NSE Code').")
        fmt = c2.selectbox("Format", list(FORMATS), format_func=FORMATS.get, key=f"{k}_fmt",
                           help="**Auto** = Percent when you divide or use growth, otherwise Number.")
        dec = c3.number_input("Decimals", 0, 4, key=f"{k}_dec")
        err, info = check(formula, view, numeric, summarize, formulas, name, True)
        if err:
            st.markdown(f'<div class="f-err">✕ {html.escape(err)}</div>', unsafe_allow_html=True)
        else:
            ex = info["sample"].dropna()
            pct = (info["fmt"] if fmt == AUTO else fmt) == "percent"
            first = f"{ex.iloc[0] * (100 if pct else 1):,.{dec}f}{'%' if pct else ''}" if len(ex) else "blank"
            st.markdown(f'<div class="f-ok">✓ Formula works · {info["n_ok"]} quarter columns · '
                        f'{info["quarter"]}: {len(ex):,} companies have a value · first company: {first}</div>',
                        unsafe_allow_html=True)
            st.caption(f"{info['quarter']} reads as: `{info['reads']}`")
            if not info["moves"]:
                st.caption("⚠️ This formula uses fixed columns only, so every quarter gets the same number "
                           "(a flat line). Use quarter columns like 'PAT Q1 FY25'.")
    with right:
        t_sheet, t_calc = st.tabs([f"Sheet columns ({len(sheet)})", f"Pivot columns ({len(others)})"])
        with t_sheet:
            q = st.text_input("Search sheet columns", key=f"{k}_sq", placeholder="Search, e.g. PAT Q2",
                              label_visibility="collapsed", icon=":material/search:")
            hits = [c for c in sheet if _matches(q, c)]
            with st.container(height=250, border=True):
                st.pills("Sheet columns", hits[:300], key=f"{k}_sp", label_visibility="collapsed",
                         on_change=_insert, args=(f"{k}_f", f"{k}_sp", "col"))
            st.caption(f"{len(hits)} of {len(sheet)} · click to add 'column'")
        with t_calc:
            q = st.text_input("Search pivot columns", key=f"{k}_cq", placeholder="Search, e.g. margin",
                              label_visibility="collapsed", icon=":material/search:")
            hits = [n for n in others.values() if _matches(q, n)]
            with st.container(height=250, border=True):
                if hits:
                    st.pills("Pivot columns", hits, key=f"{k}_cp", label_visibility="collapsed",
                             on_change=_insert, args=(f"{k}_f", f"{k}_cp", "calc"))
                else:
                    st.caption("No other calculated fields yet." if not others else "No pivot columns match.")
            st.caption(f"{len(hits)} of {len(others)} · click to add [column]")

    taken = {n.lower() for n in others.values()}
    problem = ("Give the field a name." if not name.strip() else
               "Another calculation already uses this name." if name.strip().lower() in taken else err)
    b1, b2, b3 = st.columns([3, 1, 1])
    if problem and not err:
        b1.caption(f"⚠️ {problem}")
    if b2.button("Cancel", width="stretch", key=f"{k}_cancel"):
        st.rerun()
    if b3.button("OK", type="primary", width="stretch", key=f"{k}_ok", disabled=bool(problem)):
        text = formula.strip() if formula.strip().startswith("=") else "=" + formula.strip()
        if qid is None:
            _add_query(name.strip(), text, summarize, fmt, int(dec))
        else:
            old = _query_label(qid)
            ss[_k(qid, "name")], ss[_k(qid, "f")] = name.strip(), text
            ss[_k(qid, "s")], ss[_k(qid, "fmt")], ss[_k(qid, "dec")] = summarize, fmt, int(dec)
            if old != name.strip():
                _rename_refs(old, name.strip())
        for key in [x for x in ss.keys() if str(x).startswith(k + "_")]:
            del ss[key]                                      # next open starts fresh
        st.rerun()


def _open_dialog(view: pd.DataFrame, numeric: list[str], qid: int | None = None) -> None:
    ss["calc_dlg"] = ss.get("calc_dlg", 0) + 1               # a fresh form every time it opens
    for key in [x for x in ss.keys() if str(x).startswith("cfd_")]:
        del ss[key]
    calc_dialog(view, numeric, qid)


def _toolbar(view: pd.DataFrame, numeric: list[str], levels_here: list[str]) -> None:
    """One bar, like the dashboard: Calculated field · Edit · Examples · Rows."""
    ids = _qids()
    with st.container(key="calcbar"):
        c = st.columns([1.35, 0.9, 1.05, 3.2], vertical_alignment="bottom")
        if c[0].button("Calculated field", icon=":material/function:", type="primary", width="stretch",
                       key="calc_add", help="Add a calculated field (same editor as the dashboard)"):
            _open_dialog(view, numeric)
        with c[1].popover("Edit", icon=":material/edit:", width="stretch", disabled=not ids):
            labels = {i: _query_label(i) for i in ids}
            vid = st.selectbox("Calculated field", ids, key="calc_editpick", format_func=labels.get)
            if vid in ids:
                st.code(_raw(vid) or "=", language=None)
                e1, e2 = st.columns(2)
                if e1.button("Edit formula", icon=":material/function:", width="stretch", key="calc_editf"):
                    _open_dialog(view, numeric, vid)
                e2.button("Copy", icon=":material/content_copy:", width="stretch", key="calc_copy",
                          on_click=_duplicate, args=(vid,))
                m1, m2, m3 = st.columns(3)
                pos = ids.index(vid)
                m1.button("Left", icon=":material/arrow_back:", width="stretch", key="calc_ml",
                          on_click=_move_query, args=(vid, -1), disabled=pos == 0, help="Move one table left")
                m2.button("Right", icon=":material/arrow_forward:", width="stretch", key="calc_mr",
                          on_click=_move_query, args=(vid, 1), disabled=pos == len(ids) - 1,
                          help="Move one table right")
                m3.button("Remove", icon=":material/delete:", width="stretch", key="calc_rm",
                          on_click=_remove_query, args=(vid,))
        with c[2].popover("Examples", icon=":material/lightbulb:", width="stretch"):
            for ex_name, template in EXAMPLES.items():
                ex_formula = example_formula(template, numeric)
                if ex_formula:
                    st.button(ex_name, key=f"calc_ex_{ex_name}", width="stretch", help=ex_formula,
                              on_click=_add_example, args=(ex_name, ex_formula))
        c[3].multiselect("Rows", levels_here, key="calc_levels", placeholder="Sector",
                         help="In this order, e.g. Sector › Industry Group › companies.")


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
    ss["_calc_cols"] = [_label(m) for m in by_metric]
    levels_here = [lv for lv in LEVELS if lv in view.columns]
    ss.setdefault("calc_levels", [lv for lv in ["Sector", "Industry Group"] if lv in levels_here] or levels_here[:1])
    ss["calc_levels"] = [lv for lv in ss["calc_levels"] if lv in levels_here]
    for qid in _qids():
        _migrate(qid)                                            # calculations from the old page keep working

    ui.stat_strip(view, ctx["df"])
    _toolbar(view, numeric, levels_here)
    if view.empty:
        st.warning("No companies match these filters.")
        return
    queries = _queries()
    if not queries:
        st.caption("Press **Calculated field** to make a calculation — its table and line graph appear here.")
        return

    levels = [lv for lv in LEVELS if lv in ss["calc_levels"]] or levels_here[:1]
    run = {"levels": levels}
    cols = list(dict.fromkeys([c for c in ui.TREE_COLS if c in view.columns] + numeric))
    base_cols = pivot.formula_columns(numeric)
    results = []
    for q in queries:
        if q.get("error"):
            st.markdown(f'<div class="f-err">✕ {html.escape(q["label"])}: {html.escape(q["error"])}</div>',
                        unsafe_allow_html=True)
            continue
        values, extra, error, out_fmt = prepare(view, numeric, q["text"], q["summarize"], q["fmt"], q["dec"],
                                                same=True, roll=True)
        if error and not values:
            st.markdown(f'<div class="f-err">✕ {html.escape(q["label"])}: {html.escape(error)}</div>',
                        unsafe_allow_html=True)
            continue
        if values:
            results.append((q, values, extra, out_fmt))
    if not results:
        return

    graphs = []
    tabs = st.tabs([f"📊 {q['label']}" for q, *_ in results]) if len(results) > 1 else [st.container()]
    for tab, (q, values, extra, out_fmt) in zip(tabs, results):
        with tab:
            work = pd.concat([view[cols], extra], axis=1) if len(extra.columns) else view[cols]
            tree = _tree(work, json.dumps(values), tuple(levels), tuple(base_cols + list(extra.columns)))
            _show_table(tree, q, run)
            _show_graph(q, tree, out_fmt == "percent", run)
            graphs.append((q, tree, out_fmt == "percent"))
    _show_compare(graphs, run)


def _quote_eq(col: str) -> str:
    return "=" + _quote(col)


def _show_table(tree: dict, q: dict, run: dict) -> None:
    n = len(tree["metrics"])
    ui.section(f"📋 {html.escape(q['label'])}", f"<code>{html.escape(q['raw'])}</code> · {n} quarter columns · "
               + " › ".join(run["levels"] + [COMPANY]) + " · highest first on the latest quarter")
    page = _page(json.dumps(tree), 640, ui.STYLE_VERSION)
    if hasattr(st, "iframe"):
        st.iframe(page, height="content")
    else:
        import streamlit.components.v1 as components
        components.html(page, height=700, scrolling=True)
    frame = pivot.tree_to_frame(tree, True)
    fname = re.sub(r"[^A-Za-z0-9]+", "_", q["label"]).strip("_") or "result"
    st.download_button("Download CSV", frame.to_csv(index=False).encode("utf-8-sig"), f"calculator_{fname}.csv",
                       "text/csv", key=f"calc_csv_{q['id']}", icon=":material/download:")


def _show_graph(q: dict, tree: dict, pct: bool, run: dict, header: bool = True) -> None:
    qid = q["id"]
    how = ("SUM amounts, AVERAGE margins / growth" if q["summarize"] == AUTO else q["summarize"])
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
    _draw(long, picks, list(lines.columns), "%" if pct else "Value", q["dec"], level, f"calc_chart_{qid}")
    st.caption("Gaps = that quarter doesn't have every column the formula needs (or a value is ÷0).")


def _show_compare(graphs: list, run: dict) -> None:
    """2+ calculations: one graph, a line per calculation, for the grand total or one sector / group / company."""
    if len(graphs) < 2:
        return
    ui.section("📈 All calculations together", "A line per calculation · pick the row to draw it for")
    levels = [GRAND] + run["levels"] + [COMPANY]
    if ss.get("calc_cmp_lv") not in levels:
        ss["calc_cmp_lv"] = GRAND
    c1, c2, c3 = st.columns([1.6, 1.6, 2.4], vertical_alignment="bottom")
    level = c1.segmented_control("Row", levels, key="calc_cmp_lv") or GRAND
    series = {}
    if level == GRAND:
        for q, tree, _ in graphs:
            series[q["label"]] = pd.Series((tree.get("total") or {}).get("vals") or [], index=tree["metrics"],
                                           dtype=float)
        row = GRAND
    else:
        tables = {q["label"]: line_table(tree, level) for q, tree, _ in graphs}
        first = next(iter(tables.values()))
        latest = first.ffill(axis=1).iloc[:, -1] if not first.empty else pd.Series(dtype=float)
        names = latest.sort_values(ascending=False, na_position="last").index.tolist()
        for t in tables.values():
            names += [n for n in t.index if n not in names]
        if not names:
            st.info("No values to draw.")
            return
        pkey = f"calc_cmp_pick_{level}"
        if ss.get(pkey) not in names:
            ss[pkey] = names[0]
        row = c2.selectbox(level, names, key=pkey)
        for label, t in tables.items():
            series[label] = t.loc[row] if row in t.index else pd.Series(dtype=float)
    labels = list(series)
    if not isinstance(ss.get("calc_cmp_calcs"), list):
        ss["calc_cmp_calcs"] = labels[:MAX_LINES]
    ss["calc_cmp_calcs"] = [p for p in ss["calc_cmp_calcs"] if p in labels][:MAX_LINES]
    picks = c3.multiselect("Calculations", labels, key="calc_cmp_calcs", max_selections=MAX_LINES,
                           placeholder="Pick calculations to draw")
    if not picks:
        st.info("Pick at least one calculation to draw.")
        return
    long = pd.concat([pd.DataFrame({"Line": p, "Quarter": series[p].index, "Value": series[p].to_numpy()})
                      for p in picks], ignore_index=True).dropna()
    if long.empty:
        st.info(f"No values for {row}.")
        return
    pct = {q["label"]: p for q, _, p in graphs}
    kinds = {pct[p] for p in picks}
    quarters = list(dict.fromkeys(q for _, tree, _ in graphs for q in tree["metrics"]))
    dec = max(q["dec"] for q, *_ in graphs)
    _draw(long, picks, quarters, "%" if kinds == {True} else "Value", dec, "Calculation", "calc_chart_compare")
    if len(kinds) > 1:
        st.caption("⚠️ Percent and number calculations share one axis here (percent ones are drawn as %, e.g. "
                   "12.5) — pick only one kind for a clearer graph.")


def _draw(long: pd.DataFrame, order: list, quarters: list, unit: str, dec: int, what: str, key: str) -> None:
    """Line graph: one coloured line per value of long["Line"], quarters along the bottom."""
    fmt = f",.{dec}f"
    lo, hi = float(long["Value"].min()), float(long["Value"].max())
    pad = (hi - lo) * 0.08 or max(abs(hi) * 0.05, 1.0)          # flat data still gets some room
    domain = [lo - pad, hi + pad]
    quarters_shown = [q for q in quarters if q in set(long["Quarter"])]
    base = alt.Chart(long).encode(
        x=alt.X("Quarter:N", sort=quarters_shown, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Value:Q", title=unit, axis=alt.Axis(format=fmt),
                scale=alt.Scale(domain=domain, zero=False, nice=True)),
        color=alt.Color("Line:N", title=None, sort=order,
                        legend=alt.Legend(orient="bottom", columns=3, labelLimit=280),
                        scale=alt.Scale(range=PALETTE)),
        tooltip=[alt.Tooltip("Line:N", title=what), alt.Tooltip("Quarter:N"),
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
    st.altair_chart(chart, width="stretch", theme=None, key=key)