"""Pivot logic: layouts, calculated-field formulas, summarising and sorting. No UI code here.

A *layout* is a plain dict (so it can be saved as JSON):
{
  "name":   "My view",
  "levels": ["Sector", "Industry Group"],                 # row levels, companies are always last
  "values": [                                              # columns of the pivot, in order
     {"id": "a1", "name": "OPM Q2 FY25", "column": "OPM Q2 FY25",
      "summarize": "AVERAGE", "format": "number"},
     {"id": "b2", "name": "Sales Growth Q2 vs Q1", "formula": "=('Sales Q2 FY25'/'Sales Q1 FY25')-1",
      "summarize": "CUSTOM", "format": "percent"},
  ],
  "sort": {"Sector": {"by": "", "dir": "asc"},            # by "" = by name, else a value name
           "Industry Group": {"by": "OPM Q2 FY25", "dir": "desc"},
           "Company": {"by": "", "dir": "asc"}},
}
"""

import ast
import re
import uuid

import numpy as np
import pandas as pd

from data import LEVELS

SUMMARIZE = ["SUM", "AVERAGE", "MEDIAN", "MIN", "MAX", "COUNT"]
CUSTOM = "CUSTOM"           # calculated fields only: formula applied to each group's SUMs
FORMATS = {"number": "Number", "percent": "Percent (×100 %)"}
COMPANY = "Company"
UNMAPPED = "Unmapped"

_AGG = {"SUM": "sum", "AVERAGE": "mean", "MEDIAN": "median", "MIN": "min", "MAX": "max", "COUNT": "count"}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


DEFAULT_VALUES = 10          # the default layout starts with this many columns; add more in the editor


def default_layout(numeric: list[str]) -> dict:
    return {
        "name": "Default",
        "levels": ["Sector", "Industry Group"],
        "values": [{"id": new_id(), "name": c, "column": c, "summarize": "AVERAGE", "format": "number"}
                   for c in numeric[:DEFAULT_VALUES]],
        "sort": {},
    }


def clean_layout(layout: dict, numeric: list[str]) -> dict:
    """Drop anything that no longer exists in the sheet (renamed columns etc.)."""
    lay = {**layout}
    lay["levels"] = [lv for lv in lay.get("levels", []) if lv in LEVELS] or ["Sector"]
    vals = []
    for v in lay.get("values", []):
        v = {"id": v.get("id") or new_id(), "format": "number", "summarize": "AVERAGE", **v}
        if "formula" in v or v.get("column") in numeric:
            vals.append(v)
    lay["values"] = vals
    lay["sort"] = dict(lay.get("sort", {}))
    return lay


# ---------------------------------------------------------------- formulas
class FormulaError(ValueError):
    pass


_REF = re.compile(r"'((?:[^']|'')+)'")          # 'Column name'  ('' = a literal quote)
_FUNCS = {
    "ABS": np.abs,
    "ROUND": lambda x, n=0: np.round(x, int(n)),
    "MIN": np.fmin,
    "MAX": np.fmax,
    "SQRT": np.sqrt,
    "IF": lambda c, a, b: np.where(c, a, b),
    "IFERROR": lambda x, alt: np.where(np.isfinite(np.asarray(x, dtype=float)), x, alt),
}
_OK_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
             ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd,
             ast.Compare, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq)


def compile_formula(text: str, columns: list[str]):
    """Sheets-style formula → (code, {variable: column}). Raises FormulaError with a readable message."""
    expr = (text or "").strip()
    if expr.startswith("="):
        expr = expr[1:]
    if not expr:
        raise FormulaError("Type a formula, e.g. =('Sales Q2 FY25'/'Sales Q1 FY25')-1")
    lookup = {c.lower(): c for c in columns}
    refs: dict[str, str] = {}

    def sub(m):
        name = m.group(1).replace("''", "'").strip()
        col = lookup.get(name.lower())
        if col is None:
            raise FormulaError(f"Unknown column '{name}' — it must be a number column of the results sheet.")
        var = next((k for k, v in refs.items() if v == col), None) or f"_c{len(refs)}"
        refs[var] = col
        return f" {var} "

    expr = _REF.sub(sub, expr).replace("^", "**").replace("<>", "!=")
    expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr).strip()      # Sheets "=" comparison
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise FormulaError("The formula isn't complete — check brackets and operators.") from None
    for node in ast.walk(tree):
        if not isinstance(node, _OK_NODES):
            raise FormulaError("Only + − × ÷ ^, brackets, comparisons and ABS, ROUND, MIN, MAX, "
                               "SQRT, IF, IFERROR are allowed.")
        if isinstance(node, ast.Name) and node.id not in refs and node.id.upper() not in _FUNCS:
            raise FormulaError(f"'{node.id}' isn't recognised. Put column names in single quotes, "
                               "e.g. 'Sales Q1 FY25'.")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name)
                                               and node.func.id.upper() in _FUNCS):
            raise FormulaError("Unknown function.")
    for node in ast.walk(tree):                                  # functions are case-insensitive
        if isinstance(node, ast.Call):
            node.func.id = node.func.id.upper()
    return compile(tree, "<formula>", "eval"), refs


def evaluate(code, refs: dict, source) -> np.ndarray | float:
    """source: a DataFrame (one value per row) or a dict/Series of single numbers."""
    env = {var: (np.asarray(source[col], dtype=float) if isinstance(source, pd.DataFrame)
                 else np.float64(source[col]) if pd.notna(source[col]) else np.float64("nan"))
           for var, col in refs.items()}
    with np.errstate(all="ignore"):
        out = eval(code, {"__builtins__": {}, **_FUNCS}, env)    # noqa: S307 — AST validated above
    out = np.asarray(out, dtype=float)
    out[~np.isfinite(out)] = np.nan                              # x/0 → blank, like Sheets #DIV/0!
    return out if out.ndim else float(out)


def check_formula(text: str, frame: pd.DataFrame, columns: list[str]) -> tuple[str | None, pd.Series | None]:
    """(error message or None, sample results)."""
    try:
        code, refs = compile_formula(text, columns)
        vals = evaluate(code, refs, frame)
        return None, pd.Series(np.broadcast_to(vals, len(frame)), index=frame.index)
    except FormulaError as e:
        return str(e), None
    except Exception as e:                                       # e.g. wrong number of arguments
        return f"Couldn't calculate: {e}", None


# ---------------------------------------------------------------- building the pivot
def _row_values(view: pd.DataFrame, values: list[dict], columns: list[str]) -> pd.DataFrame:
    """One column per value field, one row per company (formulas evaluated per company)."""
    out = {}
    for v in values:
        if "formula" in v:
            err, s = check_formula(v["formula"], view, columns)
            out[v["id"]] = s if s is not None else pd.Series(np.nan, index=view.index)
        else:
            out[v["id"]] = pd.to_numeric(view[v["column"]], errors="coerce")
    return pd.DataFrame(out, index=view.index)


def build_tree(view: pd.DataFrame, layout: dict, columns: list[str]) -> dict:
    """Nested rows {label, n, vals, kids}; group rows are summarised as each value field says."""
    levels, values = layout["levels"], layout["values"]
    scale = np.array([100.0 if v.get("format") == "percent" else 1.0 for v in values])
    rv = _row_values(view, values, columns)
    custom = {v["id"]: compile_formula(v["formula"], columns) for v in values
              if v.get("summarize") == CUSTOM and "formula" in v and _ok(v["formula"], columns)}
    sums_cols = sorted({c for _, refs in custom.values() for c in refs.values()})

    def summarise(idx) -> list:
        part = rv.loc[idx]
        res = []
        sums = view.loc[idx, sums_cols].sum(numeric_only=True) if custom else None
        for v in values:
            how = v.get("summarize", "AVERAGE")
            if how == CUSTOM:
                if v["id"] in custom:
                    code, refs = custom[v["id"]]
                    res.append(evaluate(code, refs, sums))
                else:
                    res.append(np.nan)
            elif how == "COUNT":
                res.append(float(part[v["id"]].count()))
            else:
                s = part[v["id"]]
                res.append(s.agg(_AGG.get(how, "mean")) if s.notna().any() else np.nan)
        return _fmt(np.asarray(res, dtype=float) * scale)

    sort = layout.get("sort", {})

    def order(rows: list, level: str) -> list:
        cfg = sort.get(level, {})
        by, desc = cfg.get("by", ""), cfg.get("dir", "asc") == "desc"
        if by and by in [v["name"] for v in values]:
            i = [v["name"] for v in values].index(by)
            have = [r for r in rows if r["vals"][i] is not None]
            missing = [r for r in rows if r["vals"][i] is None]
            return sorted(have, key=lambda r: r["vals"][i], reverse=desc) + missing   # blanks last
        return sorted(rows, key=lambda r: str(r["label"]).lower(), reverse=desc)

    company_vals = rv.to_numpy(dtype=float) * scale
    pos = {ix: n for n, ix in enumerate(view.index)}
    names = view["Name"].astype(str) if "Name" in view.columns else pd.Series("", index=view.index)
    nse = view["NSE Code"].astype(str) if "NSE Code" in view.columns else pd.Series("", index=view.index)
    bse = view["BSE Code"].astype(str) if "BSE Code" in view.columns else pd.Series("", index=view.index)
    codes = nse.where(nse != "", bse)                      # NSE code, or BSE code when there is none

    def node(idx: pd.Index, depth: int) -> list:
        if depth == len(levels):
            rows = [{"label": names[i] or "—", "code": codes[i], "vals": _fmt(company_vals[pos[i]])}
                    for i in idx]
            return order(rows, COMPANY)
        level = levels[depth]
        keys = view.loc[idx, level].replace("", UNMAPPED)
        rows = [{"label": name, "n": len(g), "vals": summarise(g), "kids": node(g, depth + 1)}
                for name, g in keys.groupby(keys, sort=False).groups.items()]
        return order(rows, level)

    return {"levels": levels, "metrics": [v["name"] for v in values],
            "formats": [v.get("format", "number") for v in values],
            "rows": node(view.index, 0),
            "total": {"n": len(view), "vals": summarise(view.index)}}


def _ok(formula: str, columns: list[str]) -> bool:
    try:
        compile_formula(formula, columns)
        return True
    except FormulaError:
        return False


def _fmt(arr) -> list:
    return [None if not np.isfinite(x) else round(float(x), 2) for x in np.asarray(arr, dtype=float)]