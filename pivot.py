"""Pivot logic, matching Google Sheets pivot tables. No UI code here.

A *layout* is a plain dict (saved as JSON):
{
  "levels":  ["Sector", "Industry Group"],          # Rows; companies are always the last level
  "values":  [                                       # Values, in column order
     {"id": "a1", "name": "COUNTA of NSE Code", "column": "NSE Code", "summarize": "COUNTA"},
     {"id": "b2", "name": "Sales Growth Q2 Vs Q1 FY25",
      "formula": "=('Sales Q2 FY25'/'Sales Q1 FY25')-1", "summarize": "SUM",
      "format": "percent", "decimals": 2, "show_as": "default"},
  ],
  "filters": [{"field": "Sales Q2 FY25", "op": ">", "value": "0"}],
  "sort":    {"Sector": {"by": "", "dir": "asc"}},   # by "" = by name, else a value's name
  "grand_total": true,
}

How a value is summarised (same as Sheets)
  • Column value       → the column is summarised (SUM, AVERAGE, COUNTA …) for each group.
  • Calculated field   → every column in the formula is summarised first, then the formula runs.
                         e.g. SUM of =('Sales Q2'/'Sales Q1')-1  =  (total Q2 ÷ total Q1) − 1
  • CUSTOM             → you write the summaries yourself: =SUM('PAT Q2')/COUNTA('NSE Code')
"""

import ast
import re
import uuid
import warnings

import numpy as np
import pandas as pd

from data import LEVELS

SUMMARIZE = ["SUM", "COUNTA", "COUNT", "COUNTUNIQUE", "AVERAGE", "MAX", "MIN", "MEDIAN",
             "PRODUCT", "STDEV", "STDEVP", "VAR", "VARP"]
CUSTOM = "CUSTOM"
TEXT_OK = ["COUNTA", "COUNTUNIQUE"]                      # the only summaries for text columns
SHOW_AS = {"default": "Default", "pct_total": "% of grand total", "pct_parent": "% of parent row"}
FORMATS = {"number": "Number", "percent": "Percent"}
COMPANY = "Company"
UNMAPPED = "Unmapped"
TEXT_FIELDS = ["NSE Code", "BSE Code", "Name"] + LEVELS   # text columns usable with COUNTA
FILTER_OPS = [">", ">=", "<", "<=", "=", "≠", "between", "is empty", "is not empty", "contains"]
DEFAULT_VALUES = 10

_ROW = {  # what each summary means for a single company row
    "SUM": "x", "AVERAGE": "x", "MEDIAN": "x", "MIN": "x", "MAX": "x", "PRODUCT": "x",
    "COUNT": "count", "COUNTA": "counta", "COUNTUNIQUE": "counta",
    "STDEV": "nan", "VAR": "nan", "STDEVP": "zero", "VARP": "zero",
}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def value_defaults(v: dict) -> dict:
    return {"summarize": "SUM", "format": "number", "decimals": 2, "show_as": "default", **v}


def default_layout(numeric: list[str]) -> dict:
    vals = [value_defaults({"id": new_id(), "name": c, "column": c, "summarize": "AVERAGE"})
            for c in numeric[:DEFAULT_VALUES]]
    return {"name": "Default", "levels": ["Sector", "Industry Group"], "values": vals,
            "filters": [], "sort": {}, "grand_total": True}


def clean_layout(layout: dict, numeric: list[str]) -> dict:
    """Fill in missing keys and drop columns that no longer exist in the sheet."""
    lay = {"filters": [], "sort": {}, "grand_total": True, **layout}
    lay["levels"] = [lv for lv in lay.get("levels", []) if lv in LEVELS] or ["Sector"]
    ok_cols = set(numeric) | set(TEXT_FIELDS)
    lay["values"] = [value_defaults({"id": v.get("id") or new_id(), **v}) for v in lay.get("values", [])
                     if "formula" in v or v.get("column") in ok_cols]
    lay["sort"] = dict(lay.get("sort") or {})
    lay["filters"] = [{"id": f.get("id") or new_id(), "field": "", "op": ">", "value": "", **f}
                      for f in (lay.get("filters") or [])]
    return lay


# ---------------------------------------------------------------- the pivot from your Google Sheet
# 'Data Analysis Quarterly' tab: Rows = Industry (BSE) › Igroup › Name, and exactly these values,
# in this order. Each pair of quarters has 6 fields: Sales Growth, OP Growth, OPM Delta, EBIT Growth,
# EBITM Delta, PAT Growth — then COUNTA of NSE Code at the end.
SHEET_QUARTERS = [(25, 1), (25, 2), (25, 3), (25, 4), (26, 1), (26, 2), (26, 3), (26, 4), (27, 1), (27, 2)]
SHEET_NAMES = [
    ["Sales Growth Q2 Vs Q1 FY25", "OP Growth Q2 Vs Q1 FY25", "OPM Delta Q2 Vs Q1 FY25",
     "EBIT Growth Q2 Vs Q1 FY25", "EBITM Delta Q2 Vs Q1 FY25", "PAT Growth Q2 Vs Q1 FY25"],
    ["Sales Growth Q3 Vs Q2 FY25", "OP Growth Q3 Vs Q2 FY25", "OPM Delta Q3 Vs Q2 FY25",
     "EBIT Growth Q3 Vs Q2 FY25", "EBITM Delta Q3 Vs Q2 FY25", "PAT Growth Q3 Vs Q2 FY25"],
    ["Sales Growth Q4 Vs Q3 FY25", "OP Growth Q4 Vs Q3 FY25", "OPM Delta Q4 Vs Q3 FY25",
     "EBIT Growth Q4 Vs Q3 FY25", "EBITM Delta Q4 Vs Q3 FY25", "PAT Growth Q4 Vs Q3 FY25"],
    ["Sales Growth Q1 Vs Q4, FY25-26", "OP Growth Q1 Vs Q4 FY26-25", "OPM Delta Q1 Vs Q4 FY26-25",
     "EBIT Growth Q1 FY26", "EBITM Delta Q1 Vs Q4 FY26-25", "PAT Growth Q1 FY26"],
    ["Sales Growth Q2 FY26", "OP Growth Q2 FY26", "OPM Delta Q2 FY26",
     "EBIT Growth Q2 FY26", "EBIT M Delta Q2 FY26", "PAT Growth Q2 FY26"],
    ["Sales Growth Q3 FY26", "OP Growth Q3 FY26", "OPM Delta Q3 FY26",
     "EBIT Growth Q3 FY26", "EBITM Delta Q3 FY26", "PAT Growth Q3 FY26"],
    ["Sales Growth Q4 FY26", "OP Growth Q4 FY26", "OPM Delta Q4 FY26",
     "EBIT Growth Q4 FY26", "EBITM Delta Q4 FY26", "PAT Growth Q4 FY26"],
    ["Sales Growth Q1 FY27", "OP Growth Q1 FY27", "OPM Delta Q1FY27",
     "EBIT Growth Q1 FY27", "EBITM Delta Q1 FY27", "PAT Growth Q1 FY27"],
    ["Sales growth Q2 FY27", "OP Growth Q2 FY27", "OPM Delta Q2 FY27",
     "EBIT Growth Q2 FY27", "EBITM Delta Q2 FY27", "PAT Growth Q2 FY27"],
]
_QCOL = re.compile(r"^(Sales|OP|OPM|EBIT|EBIT ?M|PAT)(\s+Growth)?\s+Q([1-4])\s*FY\s?(\d{2})$", re.I)


def _quarter_columns(numeric: list[str]) -> dict[tuple, str]:
    """{(metric, fy, q): column}, metric like SALES, OP, OPM, EBIT, EBITM, PAT, OP GROWTH …"""
    found = {}
    for c in numeric:
        m = _QCOL.match(c.strip())
        if m:
            metric = m.group(1).upper().replace(" ", "") + (" GROWTH" if m.group(2) else "")
            found[(metric, int(m.group(4)), int(m.group(3)))] = c
    return found


def quarterly_template(numeric: list[str]) -> dict | None:
    """Exactly the 55 values of the sheet's pivot (fields whose columns are missing are skipped):
      Sales Growth = calculated ('Sales now'/'Sales before')-1, SUM   → total ÷ total − 1
      OP / EBIT / PAT Growth = the sheet's own 'OP Growth Qx FYyy' column, AVERAGE
      OPM / EBITM Delta = calculated 'OPM now'-'OPM before', SUM
    (If a growth column isn't in the sheet, it is calculated like Sales Growth instead.)"""
    cols = _quarter_columns(numeric)
    vals = []

    def add(**v):
        vals.append(value_defaults({"id": new_id(), **v}))

    for (prev, cur), names in zip(zip(SHEET_QUARTERS, SHEET_QUARTERS[1:]), SHEET_NAMES):
        get = lambda metric, fq: cols.get((metric, *fq))                       # noqa: E731
        sales_now, sales_before = get("SALES", cur), get("SALES", prev)
        if sales_now and sales_before:
            add(name=names[0], formula=f"=('{sales_now}'/'{sales_before}')-1", summarize="SUM",
                format="percent")
        for i, metric in ((1, "OP"), (3, "EBIT"), (5, "PAT")):
            own = get(f"{metric} GROWTH", cur)
            now, before = get(metric, cur), get(metric, prev)
            if own:
                add(name=names[i], column=own, summarize="AVERAGE", format="percent")
            elif now and before:
                add(name=names[i], formula=f"=('{now}'/'{before}')-1", summarize="SUM", format="percent")
        for i, metric in ((2, "OPM"), (4, "EBITM")):
            now, before = get(metric, cur), get(metric, prev)
            if now and before:
                add(name=names[i], formula=f"=('{now}')-('{before}')", summarize="SUM", decimals=3)
    if not vals:
        return None
    vals.sort(key=lambda v: [n for row in SHEET_NAMES for n in row].index(v["name"]))   # sheet order
    add(name="COUNTA of NSE Code", column="NSE Code", summarize="COUNTA", decimals=0)
    return {"name": "Data Analysis Quarterly", "levels": ["Sector", "Industry Group"], "values": vals,
            "filters": [], "sort": {}, "grand_total": True}


# ---------------------------------------------------------------- formulas
class FormulaError(ValueError):
    pass


_REF = re.compile(r"'((?:[^']|'')+)'")                 # 'Sheet column'  ('' = a literal quote)
_VREF = re.compile(r"\[([^\[\]]+)\]")                   # [Pivot column]  (another value of this pivot)


def _f(x):
    return np.asarray(x, dtype=float)


def _round(x, n=0):                                     # Sheets ROUND: halves go away from zero
    m = 10.0 ** int(n)
    return np.sign(_f(x)) * np.floor(np.abs(_f(x)) * m + 0.5) / m


def _roundup(x, n=0):
    m = 10.0 ** int(n)
    return np.sign(_f(x)) * np.ceil(np.abs(_f(x)) * m) / m


def _rounddown(x, n=0):
    m = 10.0 ** int(n)
    return np.sign(_f(x)) * np.floor(np.abs(_f(x)) * m) / m


def _stack(args):
    shape = np.broadcast(*[_f(a) for a in args]).shape if len(args) > 1 else _f(args[0]).shape
    return np.vstack([np.broadcast_to(_f(a), shape).reshape(1, -1) for a in args]), shape


def _multi(fn, all_blank_is_blank=True):
    """SUM(a, b, …), AVERAGE(a, b, …) … across arguments; blanks are skipped like in Sheets."""
    def run(*args):
        if not args:
            raise FormulaError("This function needs at least one value.")
        if len(args) == 1:
            return _f(args[0])
        arr, shape = _stack(args)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = fn(arr, axis=0)
        if all_blank_is_blank:
            out = np.where(np.isnan(arr).all(axis=0), np.nan, out)
        return out.reshape(shape)
    return run


def _truthy(x):
    x = _f(x)
    return np.where(np.isnan(x), False, x != 0)


_SCALAR = {
    # arithmetic
    "ADD": np.add, "MINUS": np.subtract, "MULTIPLY": np.multiply, "DIVIDE": np.divide,
    "POWER": np.power, "POW": np.power, "MOD": np.mod, "ABS": np.abs, "SIGN": np.sign,
    "SQRT": np.sqrt, "EXP": np.exp, "LN": np.log, "LOG10": np.log10,
    "LOG": lambda x, base=10: np.log(_f(x)) / np.log(base),
    # rounding
    "ROUND": _round, "ROUNDUP": _roundup, "ROUNDDOWN": _rounddown, "TRUNC": _rounddown,
    "INT": np.floor,
    "CEILING": lambda x, step=1: np.ceil(_f(x) / step) * step,
    "FLOOR": lambda x, step=1: np.floor(_f(x) / step) * step,
    # across several values (with one sheet column inside they summarise it instead — see below)
    "SUM": _multi(np.nansum), "AVERAGE": _multi(np.nanmean), "MEDIAN": _multi(np.nanmedian),
    "MIN": _multi(np.nanmin), "MAX": _multi(np.nanmax), "PRODUCT": _multi(np.nanprod),
    # logic
    "IF": lambda c, a, b=np.nan: np.where(_truthy(c), a, b),
    "IFERROR": lambda x, alt=0: np.where(np.isfinite(_f(x)), x, alt),
    "AND": lambda *a: np.logical_and.reduce([_truthy(x) for x in a]).astype(float),
    "OR": lambda *a: np.logical_or.reduce([_truthy(x) for x in a]).astype(float),
    "NOT": lambda x: (~_truthy(x)).astype(float),
    "ISBLANK": lambda x: np.isnan(_f(x)).astype(float),
    # trigonometry & constants
    "PI": lambda: np.pi, "SIN": np.sin, "COS": np.cos, "TAN": np.tan,
    "DEGREES": np.degrees, "RADIANS": np.radians,
}
_AGGS = set(SUMMARIZE)
_OK_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
             ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd,
             ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq)

# shown in the formula box: (name, what gets inserted, explanation)
FUNCTIONS = [
    ("ADD", "ADD(", "ADD(a, b) → a + b"), ("MINUS", "MINUS(", "MINUS(a, b) → a − b"),
    ("MULTIPLY", "MULTIPLY(", "MULTIPLY(a, b) → a × b"), ("DIVIDE", "DIVIDE(", "DIVIDE(a, b) → a ÷ b"),
    ("POWER", "POWER(", "POWER(a, n) → a to the power n (same as a^n)"),
    ("MOD", "MOD(", "MOD(a, b) → remainder of a ÷ b"),
    ("ABS", "ABS(", "ABS(x) → x without its minus sign"), ("SIGN", "SIGN(", "SIGN(x) → 1, 0 or −1"),
    ("SQRT", "SQRT(", "SQRT(x) → square root"), ("EXP", "EXP(", "EXP(x) → e to the power x"),
    ("LN", "LN(", "LN(x) → natural log"), ("LOG", "LOG(", "LOG(x, base) → log (base 10 if left out)"),
    ("LOG10", "LOG10(", "LOG10(x) → log base 10"),
    ("ROUND", "ROUND(", "ROUND(x, places) → normal rounding"),
    ("ROUNDUP", "ROUNDUP(", "ROUNDUP(x, places) → always away from zero"),
    ("ROUNDDOWN", "ROUNDDOWN(", "ROUNDDOWN(x, places) → always towards zero"),
    ("TRUNC", "TRUNC(", "TRUNC(x, places) → cut off decimals"), ("INT", "INT(", "INT(x) → round down to a whole number"),
    ("CEILING", "CEILING(", "CEILING(x, step) → up to the next multiple of step"),
    ("FLOOR", "FLOOR(", "FLOOR(x, step) → down to the multiple of step"),
    ("SUM", "SUM(", "SUM('column') → group total · SUM(a, b, …) → adds the values"),
    ("AVERAGE", "AVERAGE(", "AVERAGE('column') → group average · AVERAGE(a, b, …) → mean of the values"),
    ("MEDIAN", "MEDIAN(", "MEDIAN('column') or MEDIAN(a, b, …)"),
    ("MIN", "MIN(", "MIN('column') → group minimum · MIN(a, b, …) → smallest value"),
    ("MAX", "MAX(", "MAX('column') → group maximum · MAX(a, b, …) → largest value"),
    ("PRODUCT", "PRODUCT(", "PRODUCT('column') or PRODUCT(a, b, …) → multiplies"),
    ("COUNT", "COUNT(", "COUNT('column') → companies with a number"),
    ("COUNTA", "COUNTA(", "COUNTA('column') → companies with any value, e.g. COUNTA('NSE Code')"),
    ("COUNTUNIQUE", "COUNTUNIQUE(", "COUNTUNIQUE('column') → distinct values"),
    ("STDEV", "STDEV(", "STDEV('column') → standard deviation (sample)"),
    ("STDEVP", "STDEVP(", "STDEVP('column') → standard deviation (population)"),
    ("VAR", "VAR(", "VAR('column') → variance (sample)"), ("VARP", "VARP(", "VARP('column') → variance (population)"),
    ("IF", "IF(", "IF(condition, value if true, value if false)"),
    ("IFERROR", "IFERROR(", "IFERROR(x, fallback) → fallback when x is blank / ÷0"),
    ("AND", "AND(", "AND(a > 0, b > 0) → true when all are true"),
    ("OR", "OR(", "OR(a > 0, b > 0) → true when any is true"), ("NOT", "NOT(", "NOT(condition)"),
    ("ISBLANK", "ISBLANK(", "ISBLANK(x) → true when x is empty"),
    ("PI", "PI()", "PI() → 3.14159…"), ("SIN", "SIN(", "SIN(x)"), ("COS", "COS(", "COS(x)"),
    ("TAN", "TAN(", "TAN(x)"), ("DEGREES", "DEGREES(", "DEGREES(x) → radians to degrees"),
    ("RADIANS", "RADIANS(", "RADIANS(x) → degrees to radians"),
]
FUNCTIONS_HELP = ("'Sheet column' · [Pivot column] · + − × ÷ ^ % ( ) · > < = <> · "
                  "every function in the Function list")

# quick "A ⊕ B" builder: label → (formula template, suggested format)
QUICK_OPS = {
    "A + B": ("{a} + {b}", None), "A − B": ("{a} - {b}", None), "A × B": ("{a} * {b}", None),
    "A ÷ B": ("{a} / {b}", None), "% change of A vs B": ("({a} / {b}) - 1", "percent"),
    "A as % of B": ("{a} / {b}", "percent"), "A ^ B": ("{a} ^ {b}", None),
    "Average of A and B": ("AVERAGE({a}, {b})", None), "Smaller of A, B": ("MIN({a}, {b})", None),
    "Larger of A, B": ("MAX({a}, {b})", None),
}


class Formula:
    """A compiled formula. `cols`: variable → (sheet column, summary); `deps`: variable → value id."""

    def __init__(self, code, cols: dict[str, tuple[str, str]], deps: dict[str, str] | None = None):
        self.code, self.cols, self.deps = code, cols, deps or {}


def compile_formula(text: str, columns: list[str], summarize: str = "SUM",
                    values: dict[str, str] | None = None, self_name: str = "") -> Formula:
    """Sheets-style formula → Formula.  values: {pivot column name (lower case): value id}."""
    expr = (text or "").strip()
    if expr.startswith("="):
        expr = expr[1:]
    if not expr.strip():
        raise FormulaError("Type a formula, e.g. =('Sales Q2 FY25'/'Sales Q1 FY25')-1")
    lookup = {c.lower(): c for c in columns}
    values = values or {}
    refs: dict[str, str] = {}
    vrefs: dict[str, str] = {}

    def sub(m):
        name = m.group(1).replace("''", "'").strip()
        col = lookup.get(name.lower())
        if col is None:
            raise FormulaError(f"Unknown sheet column '{name}'. Click it in the Columns list to insert the exact name.")
        var = next((k for k, v in refs.items() if v == col), None) or f"_c{len(refs)}"
        refs[var] = col
        return f" {var} "

    def vsub(m):
        name = m.group(1).strip()
        if self_name and name.lower() == self_name.strip().lower():
            raise FormulaError("A field can't use itself.")
        vid = values.get(name.lower())
        if vid is None:
            raise FormulaError(f"Unknown pivot column [{name}]. Click it in the Pivot columns list to insert it.")
        var = next((k for k, v in vrefs.items() if v == vid), None) or f"_v{len(vrefs)}"
        vrefs[var] = vid
        return f" {var} "

    expr = _REF.sub(sub, expr)
    expr = _VREF.sub(vsub, expr)
    for a, b in (("−", "-"), ("×", "*"), ("÷", "/"), ("^", "**"), ("<>", "!="), ("≠", "!="),
                 ("≥", ">="), ("≤", "<=")):
        expr = expr.replace(a, b)
    expr = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)            # 5% → 0.05, like Sheets
    if "%" in expr:
        raise FormulaError("Use MOD(a, b) for a remainder — % only works after a number, e.g. 5%.")
    expr = re.sub(r"\bTRUE\b", "1", expr, flags=re.I)
    expr = re.sub(r"\bFALSE\b", "0", expr, flags=re.I)
    expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr).strip()            # Sheets "=" comparison
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise FormulaError("The formula isn't complete — check brackets, commas and operators.") from None

    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, _OK_NODES):
            raise FormulaError("Only + − × ÷ ^ %, brackets, comparisons and the listed functions are allowed.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise FormulaError("Text isn't allowed — put sheet columns in 'single quotes' and pivot columns in [brackets].")
        if isinstance(node, ast.Compare) and len(node.ops) > 1:
            raise FormulaError("Compare one pair at a time, e.g. AND(a > 0, a < 10).")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise FormulaError("Unknown function.")
            node.func.id = node.func.id.upper()
            if node.func.id not in _SCALAR and node.func.id not in _AGGS:
                raise FormulaError(f"Unknown function {node.func.id}. Pick one from the Function list.")
            called.add(id(node.func))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in called and node.id not in refs and node.id not in vrefs:
            raise FormulaError(f"'{node.id}' isn't recognised. Put sheet columns in 'single quotes' "
                               "(e.g. 'Sales Q1 FY25') and pivot columns in [brackets].")

    cols: dict[str, tuple[str, str]] = {}
    deps: dict[str, str] = {}
    default = "SUM" if summarize == CUSTOM else summarize

    def var_for(key):
        var = next((k for k, v in cols.items() if v == key), None) or f"_a{len(cols)}"
        cols[var] = key
        return var

    class Agg(ast.NodeTransformer):       # SUM('x') → the summarised column; [x] → the pivot value
        def visit_Call(self, node):
            f = node.func.id
            one_col = len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id in refs
            if f in _AGGS and one_col:
                var = var_for((refs[node.args[0].id], f))
                return ast.copy_location(ast.Name(id=var, ctx=ast.Load()), node)
            if f not in _SCALAR:
                raise FormulaError(f"{f}() needs one sheet column, e.g. {f}('NSE Code').")
            self.generic_visit(node)
            return node

        def visit_Name(self, node):
            if node.id in refs:                                         # a bare sheet column
                var = var_for((refs[node.id], default))
                return ast.copy_location(ast.Name(id=var, ctx=ast.Load()), node)
            if node.id in vrefs:                                        # a pivot column
                var = "_d" + node.id[2:]
                deps[var] = vrefs[node.id]
                return ast.copy_location(ast.Name(id=var, ctx=ast.Load()), node)
            return node

    tree = ast.fix_missing_locations(Agg().visit(tree))
    return Formula(compile(tree, "<formula>", "eval"), cols, deps)


def _run(f: Formula, env: dict) -> np.ndarray:
    with np.errstate(all="ignore"):
        out = eval(f.code, {"__builtins__": {}, **_SCALAR}, env)    # noqa: S307 — AST validated above
    out = np.array(out, dtype=float, copy=True)                    # own, writable copy
    out[~np.isfinite(out)] = np.nan                                 # x/0 → blank, like #DIV/0!
    return out


# ---------------------------------------------------------------- summarising
def _prep(view: pd.DataFrame, cols: set[str]) -> pd.DataFrame:
    """Copy of every column a value needs: numbers as floats, text as text (blank → missing)."""
    out = {}
    for c in cols:
        s = view[c]
        if c in TEXT_FIELDS or not pd.api.types.is_numeric_dtype(s):
            out[c] = s.astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "<NA>": np.nan,
                                                        "None": np.nan})
        else:
            out[c] = pd.to_numeric(s, errors="coerce").astype(float)
    return pd.DataFrame(out, index=view.index)


def _agg(g, how: str, text: bool):
    """Summarise a column (or a grouped column). Text columns only support COUNTA / COUNTUNIQUE;
    COUNT of text is 0 and number summaries of text are blank — the same as Sheets."""
    if text and how not in TEXT_OK:
        return g.count() * (0 if how == "COUNT" else np.nan)
    return {"SUM": lambda: g.sum(min_count=1), "AVERAGE": g.mean, "MEDIAN": g.median, "MIN": g.min,
            "MAX": g.max, "COUNT": g.count, "COUNTA": g.count, "COUNTUNIQUE": g.nunique,
            "PRODUCT": lambda: g.prod(min_count=1),
            "STDEV": lambda: g.std(ddof=1), "STDEVP": lambda: g.std(ddof=0),
            "VAR": lambda: g.var(ddof=1), "VARP": lambda: g.var(ddof=0)}[how]()


def _row_env(data: pd.DataFrame, vars_: dict) -> dict:
    env = {}
    for var, (col, how) in vars_.items():
        s = data[col]
        kind = _ROW[how]
        if kind == "x":
            env[var] = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        elif kind == "count":
            env[var] = pd.to_numeric(s, errors="coerce").notna().to_numpy(dtype=float)
        elif kind == "counta":
            env[var] = s.notna().to_numpy(dtype=float)
        elif kind == "zero":
            env[var] = np.where(pd.to_numeric(s, errors="coerce").notna(), 0.0, np.nan)
        else:
            env[var] = np.full(len(s), np.nan)
    return env


def _group_env(data: pd.DataFrame, gb, vars_: dict, index, memo: dict) -> dict:
    """Summarised columns per group (gb = a groupby, or None for the grand total). `memo`
    remembers each (column, summary) so 55 formulas don't repeat the same work."""
    env = {}
    for var, key in vars_.items():
        if key not in memo:
            col, how = key
            text = not pd.api.types.is_numeric_dtype(data[col])
            if gb is not None:
                memo[key] = pd.Series(_agg(gb[col], how, text)).reindex(index).to_numpy(dtype=float)
            else:
                memo[key] = np.array([float(_agg(data[col], how, text))])
        env[var] = memo[key]
    return env


def _value_formula(v: dict, columns: list[str], vmap: dict[str, str] | None = None) -> Formula:
    if "formula" in v:
        others = {k: i for k, i in (vmap or {}).items() if i != v.get("id")}
        return compile_formula(v["formula"], columns, v.get("summarize", "SUM"), others, v.get("name", ""))
    how = v.get("summarize", "SUM")
    if how == CUSTOM:
        how = "SUM"
    if v["column"] in TEXT_FIELDS and how not in TEXT_OK:
        how = "COUNTA"
    return Formula(compile("_a0", "<col>", "eval"), {"_a0": (v["column"], how)})


def formula_columns(numeric: list[str]) -> list[str]:
    """Columns a formula may use: every number column, plus text columns for COUNTA()."""
    return list(numeric) + [c for c in TEXT_FIELDS if c not in numeric]


def compile_values(values: list[dict], columns: list[str]):
    """Compile every value and work out the order to calculate them in (a field that uses
    [another field] comes after it). Returns (forms, deps, order, errors {value id: message})."""
    vmap = {v["name"].strip().lower(): v["id"] for v in values}
    idx = {v["id"]: i for i, v in enumerate(values)}
    forms, errors = [], {}
    for v in values:
        try:
            forms.append(_value_formula(v, columns, vmap))
        except FormulaError as e:
            forms.append(None)
            errors[v["id"]] = str(e)
    deps = [{var: idx[vid] for var, vid in f.deps.items()} if f else {} for f in forms]
    users: list[list[int]] = [[] for _ in values]
    waiting = [len(set(d.values())) for d in deps]
    for j, d in enumerate(deps):
        for k in set(d.values()):
            users[k].append(j)
    order, queue = [], [j for j, w in enumerate(waiting) if w == 0]
    while queue:
        j = queue.pop(0)
        order.append(j)
        for u in users[j]:
            waiting[u] -= 1
            if waiting[u] == 0:
                queue.append(u)
    done = set(order)
    for j, v in enumerate(values):
        if j not in done:
            forms[j] = None
            errors.setdefault(v["id"], "Circular: this field uses itself through other pivot columns.")
    for j in order:
        if forms[j] and any(forms[k] is None for k in deps[j].values()):
            errors.setdefault(values[j]["id"], "Uses a pivot column that has an error.")
    return forms, deps, order, errors


def _compute(compiled, env_for, n: int) -> np.ndarray:
    """Every value for n rows (companies or groups), in dependency order."""
    forms, deps, order, _ = compiled
    out = np.full((n, len(forms)), np.nan)
    for j in order:
        f = forms[j]
        if f is None:
            continue
        env = dict(env_for(f))
        for var, k in deps[j].items():
            env[var] = out[:, k]
        try:
            out[:, j] = np.broadcast_to(_run(f, env), n)
        except Exception:                                            # e.g. a function given wrong arguments
            out[:, j] = np.nan
    return out


def company_values(frame: pd.DataFrame, values: list[dict], columns: list[str], compiled=None) -> pd.DataFrame:
    """Each value field for each company (what the company rows show, before % formatting)."""
    compiled = compiled or compile_values(values, columns)
    data = _prep(frame, {c for f in compiled[0] if f for c, _ in f.cols.values()})
    out = _compute(compiled, lambda f: _row_env(data, f.cols), len(frame))
    return pd.DataFrame(out, index=frame.index, columns=[v["id"] for v in values])


def check_formula(text: str, frame: pd.DataFrame, columns: list[str], summarize: str = "SUM",
                  values: list[dict] | None = None, self_id: str | None = None, self_name: str = ""):
    """(error or None, per-company results) — used by the formula box for its live check."""
    others = [v for v in (values or []) if v["id"] != self_id]
    try:
        f = compile_formula(text, columns, summarize, {v["name"].strip().lower(): v["id"] for v in others},
                            self_name)
        data = _prep(frame, {c for c, _ in f.cols.values()})
        env = _row_env(data, f.cols)
        if f.deps:
            compiled = compile_values(others, columns)
            bad = [v["name"] for v in others if v["id"] in set(f.deps.values()) and v["id"] in compiled[3]]
            if bad:
                return f"[{bad[0]}] has an error itself — fix that field first.", None
            cv = company_values(frame, others, columns, compiled)
            for var, vid in f.deps.items():
                env[var] = cv[vid].to_numpy()
        return None, pd.Series(np.broadcast_to(_run(f, env), len(frame)), index=frame.index)
    except FormulaError as e:
        return str(e), None
    except Exception as e:                                         # e.g. wrong number of arguments
        return f"Couldn't calculate: {e}", None


def apply_filters(view: pd.DataFrame, filters: list[dict], layout_values: list[dict],
                  columns: list[str], compiled=None) -> pd.DataFrame:
    """Keep only companies that pass every filter (like Sheets' Filters → Filter by condition)."""
    keep = pd.Series(True, index=view.index)
    by_name = {v["name"]: v for v in layout_values}
    cv = None
    for flt in filters:
        field, op, raw = flt.get("field"), flt.get("op"), str(flt.get("value", "")).strip()
        if not field or not op:
            continue
        if field in view.columns:
            s = view[field]
        elif field in by_name:                                     # a value field, per company
            if cv is None:
                cv = company_values(view, layout_values, columns, compiled)
            s = cv[by_name[field]["id"]]
            if by_name[field].get("format") == "percent" and op not in ("is empty", "is not empty", "contains"):
                s = s * 100                                         # "Sales Growth > 5" means 5 %
        else:
            continue
        num = pd.to_numeric(s, errors="coerce")
        text = s.astype(str).str.strip()
        empty = text.isin(["", "nan", "<NA>", "None"]) & num.isna()
        if op == "is empty":
            keep &= empty
        elif op == "is not empty":
            keep &= ~empty
        elif op == "contains":
            keep &= text.str.lower().str.contains(raw.lower(), regex=False)
        elif op == "between":
            lo, _, hi = raw.replace(" and ", ",").partition(",")
            try:
                keep &= num.between(float(lo.rstrip("% ")), float(hi.rstrip("% "))).fillna(False)
            except ValueError:
                pass
        else:
            try:
                x = float(raw.replace(",", "").rstrip("%"))
                cmp = {">": num > x, ">=": num >= x, "<": num < x, "<=": num <= x,
                       "=": num == x, "≠": num != x}[op]
                keep &= cmp.fillna(False)
            except ValueError:
                if op in ("=", "≠"):
                    eq = text.str.lower() == raw.lower()
                    keep &= eq if op == "=" else ~eq
    return view[keep]


# ---------------------------------------------------------------- building the pivot
def _tup(k) -> tuple:
    return k if isinstance(k, tuple) else (k,)


def build_tree(view: pd.DataFrame, layout: dict, columns: list[str], show: list[str] | None = None) -> dict:
    """Nested rows {label, n, vals, kids}. Group rows are summarised exactly like Sheets.
    show: value ids to display (None = all); hidden values still feed formulas and sorting."""
    levels, values = layout["levels"], layout["values"]
    compiled = compile_values(values, columns)
    forms = compiled[0]
    work = view.copy()
    for lv in levels:
        work[lv] = work[lv].replace("", UNMAPPED)
    work = apply_filters(work, layout.get("filters", []), values, columns, compiled)

    need = {c for f in forms if f for c, _ in f.cols.values()}
    data = _prep(work, need - set(levels))
    for lv in levels:
        data[lv] = work[lv]
    for c in need & set(levels):                                     # e.g. COUNTA of Sector
        data[c] = work[c]

    depth_keys, depth_vals = [], []
    for d in range(len(levels)):
        gb = data.groupby(levels[: d + 1], sort=False)
        sizes = gb.size()
        depth_keys.append(sizes)
        memo: dict = {}
        depth_vals.append(_compute(compiled, lambda f: _group_env(data, gb, f.cols, sizes.index, memo), len(sizes)))
    leaf_vals = _compute(compiled, lambda f: _row_env(data, f.cols), len(data))
    memo = {}
    total = _compute(compiled, lambda f: _group_env(data, None, f.cols, None, memo), 1)[0]

    # Show as: % of grand total / % of parent row
    np.seterr(divide="ignore", invalid="ignore")
    lookups = [{_tup(k): i for i, k in enumerate(s.index)} for s in depth_keys]
    paths = [tuple(r) for r in data[levels].itertuples(index=False)]
    for j, v in enumerate(values):
        mode = v.get("show_as", "default")
        if mode == "pct_total":
            t = total[j]
            for arr in depth_vals + [leaf_vals]:
                arr[:, j] = arr[:, j] / t if t else np.nan
            total[j] = 1.0 if t else np.nan
        elif mode == "pct_parent":
            last = len(levels) - 1
            pk = [lookups[last][p] for p in paths]
            leaf_vals[:, j] = leaf_vals[:, j] / depth_vals[last][pk, j]
            for d in range(last, 0, -1):
                pk = [lookups[d - 1][_tup(k)[:d]] for k in depth_keys[d].index]
                depth_vals[d][:, j] = depth_vals[d][:, j] / depth_vals[d - 1][pk, j]
            t = total[j]
            depth_vals[0][:, j] = depth_vals[0][:, j] / t if t else np.nan
            total[j] = 1.0 if t else np.nan

    pct = [v.get("format") == "percent" or v.get("show_as", "default") != "default" for v in values]
    scale = np.array([100.0 if p else 1.0 for p in pct])
    digits = [int(v.get("decimals", 2)) for v in values]

    def fmt(arr) -> list:
        arr = np.asarray(arr, dtype=float) * scale
        return [None if not np.isfinite(x) else round(float(x), d + 1) for x, d in zip(arr, digits)]

    sort = layout.get("sort", {})
    names = [v["name"] for v in values]

    def order(rows: list, level: str) -> list:
        cfg = sort.get(level, {})
        by, desc = cfg.get("by", ""), cfg.get("dir", "asc") == "desc"
        if by in names:
            i = names.index(by)
            have = [r for r in rows if r["vals"][i] is not None]
            return (sorted(have, key=lambda r: r["vals"][i], reverse=desc)
                    + [r for r in rows if r["vals"][i] is None])              # blanks last
        return sorted(rows, key=lambda r: str(r["label"]).lower(), reverse=desc)

    def col(c):
        return view.loc[work.index, c].astype(str) if c in view.columns else pd.Series("", index=work.index)

    nse, bse = col("NSE Code"), col("BSE Code")
    code = nse.where(nse.str.strip() != "", bse)
    leaves: dict[tuple, list] = {}
    for n, (path, lab, cd) in enumerate(zip(paths, col("Name"), code)):
        leaves.setdefault(path, []).append({"label": lab or "—", "code": cd, "vals": fmt(leaf_vals[n])})

    children: list[dict[tuple, list]] = [dict() for _ in levels]
    for d in range(len(levels) - 1, -1, -1):
        for i, k in enumerate(depth_keys[d].index):
            k = _tup(k)
            kids = (order(leaves.get(k, []), COMPANY) if d == len(levels) - 1
                    else order(children[d + 1].get(k, []), levels[d + 1]))
            children[d].setdefault(k[:-1], []).append(
                {"label": k[-1], "n": int(depth_keys[d].iloc[i]), "vals": fmt(depth_vals[d][i]), "kids": kids})
    rows = order(children[0].get((), []), levels[0])
    total_vals = fmt(total)

    keep = list(range(len(values))) if show is None else [j for j, v in enumerate(values) if v["id"] in set(show)]
    if len(keep) != len(values):                                   # only the searched columns
        def trim(items):
            for r in items:
                r["vals"] = [r["vals"][j] for j in keep]
                if "kids" in r:
                    trim(r["kids"])
        trim(rows)
        total_vals = [total_vals[j] for j in keep]
    return {"levels": levels, "metrics": [names[j] for j in keep],
            "formats": ["percent" if pct[j] else "number" for j in keep],
            "decimals": [digits[j] for j in keep], "rows": rows,
            "total": {"n": len(work), "vals": total_vals} if layout.get("grand_total", True) else None}


# ---------------------------------------------------------------- export
def tree_to_frame(tree: dict, companies: bool = True) -> pd.DataFrame:
    """The pivot as a flat table for CSV / Excel: one row per sector, group (and company),
    in the same order as on screen, with a Grand Total row at the end."""
    levels, metrics = tree["levels"], tree["metrics"]
    heads = [m + (" (%)" if f == "percent" else "") for m, f in zip(metrics, tree["formats"])]
    out = []

    def walk(rows, path):
        for r in rows:
            if "kids" in r:
                p = path + [r["label"]]
                kind = f"{levels[len(p) - 1]} total"
                out.append([kind] + p + [""] * (len(levels) - len(p)) + ["", "", r["n"]] + r["vals"])
                walk(r["kids"], p)
            elif companies:
                out.append(["Company"] + path + [r["label"], r.get("code", ""), 1] + r["vals"])

    walk(tree["rows"], [])
    if tree.get("total"):
        out.append(["Grand total"] + [""] * len(levels) + ["", "", tree["total"]["n"]] + tree["total"]["vals"])
    return pd.DataFrame(out, columns=["Row"] + levels + ["Company", "Code", "Companies"] + heads)