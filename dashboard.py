"""Main page: expandable pivot (Sector › Industry Group › Company) + a Google-Sheets-style pivot editor.

Pivot editor (same sections as Google Sheets)
  Rows     – levels, their order, and how each level is sorted (by name or by any value, asc/desc)
  Values   – columns or calculated fields; Summarize by, Show as, format, decimals; rename / reorder / delete
  Filters  – keep only companies that meet conditions (e.g. Sales Growth > 0, NSE Code is not empty)
  Layouts  – save / save as / open / delete (stored by storage.py)
Above the table: search columns (show only matching ones) · delete columns · undo delete
Formulas: 'Sheet column' and [Pivot column], + − × ÷ ^ % and every function in pivot.FUNCTIONS
"""

import copy
import html
import json
import re

import pandas as pd
import streamlit as st

import pivot
import storage
import ui
from data import LEVELS

ss = st.session_state
NEW = "＋ New layout"
SUMMARIZE_ALL = pivot.SUMMARIZE + [pivot.CUSTOM]
SHOW_AS_LABEL = pivot.SHOW_AS                               # key → label
SHOW_AS_KEY = {v: k for k, v in SHOW_AS_LABEL.items()}       # label → key
OPERATORS = ["+", "−", "×", "÷", "^", "%", "(", ")", ",", ">", "<", ">=", "<=", "=", "<>"]
FN_HELP = {name: helptext for name, _, helptext in pivot.FUNCTIONS}
FN_INSERT = {name: ins for name, ins, _ in pivot.FUNCTIONS}


# ---------------------------------------------------------------- working layout in session state
def _snapshot(layout: dict) -> str:
    return json.dumps({k: layout.get(k) for k in ("levels", "values", "filters", "sort", "grand_total")},
                      sort_keys=True)


def _bump() -> None:
    """Values changed outside the values table (added, edited in the formula box, new layout…)."""
    ss.pv_vbase = copy.deepcopy(ss.pv["values"])
    ss.pv_vver = ss.get("pv_vver", 0) + 1


def _set_working(layout: dict, saved: bool) -> None:
    ss.pv = layout
    ss.pv_undo = None
    ss.pv_saved = _snapshot(layout) if saved else ""
    ss.pv_gen = ss.get("pv_gen", 0) + 1                      # fresh widget keys
    _bump()


def _open(name: str, numeric: list[str]) -> None:
    saved = ss.pv_layouts.get(name)
    if saved:
        lay = pivot.clean_layout(copy.deepcopy(saved), numeric)
        lay["name"] = name
        _set_working(lay, True)
    else:                                                     # nothing saved yet: start like your sheet
        _set_working(pivot.quarterly_template(numeric) or pivot.default_layout(numeric), False)


def _init(numeric: list[str]) -> None:
    if "pv_layouts" not in ss:
        ss.pv_layouts = storage.load_all()
    if "pv" not in ss:
        _open(next(iter(ss.pv_layouts), ""), numeric)


def _is_saved() -> bool:
    return ss.pv["name"] in ss.pv_layouts


def _dirty() -> bool:
    return not _is_saved() or _snapshot(ss.pv) != ss.pv_saved


def _save(name: str) -> bool:
    lay = copy.deepcopy(ss.pv)
    lay["name"] = name
    layouts = {**ss.pv_layouts, name: lay}
    if storage.save_all(layouts):
        ss.pv_layouts, ss.pv["name"], ss.pv_saved = layouts, name, _snapshot({**ss.pv, "name": name})
        return True
    return False


def _rename_refs(old: str, new: str) -> None:
    """A pivot column was renamed: keep sorting, filters and [formulas] pointing at it."""
    for cfg in ss.pv["sort"].values():
        if cfg.get("by") == old:
            cfg["by"] = new
    for f in ss.pv["filters"]:
        if f.get("field") == old:
            f["field"] = new
    pattern = re.compile(r"\[\s*" + re.escape(old) + r"\s*\]", re.I)
    for v in ss.pv["values"]:
        if "formula" in v:
            v["formula"] = pattern.sub(lambda _: f"[{new}]", v["formula"])


def _matches(query: str, name: str) -> bool:
    """Column search: every word must appear; use commas for 'either', e.g. "pat q2, sales q2"."""
    q = (query or "").strip().lower()
    if not q:
        return True
    n = name.lower()
    return any(all(w in n for w in alt.split()) for alt in q.split(",") if alt.strip())


def _users_of(ids: set[str]) -> list[str]:
    """Names of other fields whose formula uses one of these pivot columns."""
    names = [v["name"].lower() for v in ss.pv["values"] if v["id"] in ids]
    out = []
    for v in ss.pv["values"]:
        if v["id"] not in ids and "formula" in v:
            used = {m.strip().lower() for m in re.findall(r"\[([^\[\]]+)\]", v["formula"])}
            if used & set(names):
                out.append(v["name"])
    return out


def _delete(ids: list[str]) -> None:
    """Delete pivot columns (undo-able until the next delete)."""
    ids = set(ids)
    gone = {v["name"] for v in ss.pv["values"] if v["id"] in ids}
    if not gone:
        return
    ss.pv_undo = {k: copy.deepcopy(ss.pv[k]) for k in ("values", "sort", "filters")}
    ss.pv["values"] = [v for v in ss.pv["values"] if v["id"] not in ids]
    for cfg in ss.pv["sort"].values():
        if cfg.get("by") in gone:
            cfg["by"] = ""
    ss.pv["filters"] = [f for f in ss.pv["filters"] if f.get("field") not in gone]
    ss.pv_gen += 1                                           # sort / filter boxes forget the deleted names
    _bump()
    st.toast(f"Deleted {len(gone)} column{'s' if len(gone) > 1 else ''} · press Undo to bring "
             f"{'them' if len(gone) > 1 else 'it'} back", icon="🗑️")


def _undo() -> None:
    if ss.get("pv_undo"):
        ss.pv.update(ss.pv_undo)
        ss.pv_undo = None
        ss.pv_gen += 1
        _bump()


# ---------------------------------------------------------------- dialogs
@st.dialog("Save layout as")
def save_as_dialog():
    name = st.text_input("Layout name", value="" if not _is_saved() else f'{ss.pv["name"]} copy',
                         placeholder="e.g. Q2 FY27 results", max_chars=60)
    exists = name.strip() in ss.pv_layouts
    if exists:
        st.warning("A layout with this name exists — saving will replace it.")
    st.caption(f"Saved to {storage.where()}.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button("Replace" if exists else "Save", type="primary", width="stretch", disabled=not name.strip()):
        if _save(name.strip()):
            st.toast(f"Saved “{name.strip()}”", icon="✅")
            st.rerun()


@st.dialog("Delete layout")
def delete_dialog(numeric):
    name = ss.pv["name"]
    st.write(f"Delete **{html.escape(name)}**? This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button("Delete", type="primary", width="stretch"):
        layouts = {k: v for k, v in ss.pv_layouts.items() if k != name}
        if storage.save_all(layouts):
            ss.pv_layouts = layouts
            _open(next(iter(layouts), ""), numeric)
            st.toast(f"Deleted “{name}”", icon="🗑️")
            st.rerun()


@st.dialog("Replace with the quarterly pivot?")
def template_dialog(numeric):
    tpl = pivot.quarterly_template(numeric)
    st.write(f"This builds **{len(tpl['values'])} fields** like your *Data Analysis Quarterly* sheet: "
             "Sales / OP / EBIT / PAT growth and OPM / EBITM change for every pair of quarters, plus "
             "COUNTA of NSE Code. Your current layout on screen is replaced (saved layouts are kept).")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button("Build it", type="primary", width="stretch"):
        _set_working(tpl, False)
        st.rerun()


def _append(fkey: str, token: str) -> None:
    text = ss.get(fkey, "") or "="
    joiner = "" if text.endswith(("=", "(", " ")) or token in (")", ",") else " "
    ss[fkey] = f"{text}{joiner}{token}"


def _ref(kind: str, name: str) -> str:
    return f"[{name}]" if kind == "val" else "'" + name.replace("'", "''") + "'"


def _insert(fkey: str, pkey: str, kind: str):
    """Clicked an operator, a sheet column or a pivot column → add it to the end of the formula."""
    token = ss.get(pkey)
    if token:
        _append(fkey, _ref(kind, token) if kind in ("col", "val") else token)
        ss[pkey] = None


def _insert_fn(fkey: str, skey: str):
    _append(fkey, FN_INSERT[ss[skey]])


def _quick(k: str):
    """Quick builder: A ⊕ B → a ready formula (replaces what is in the box)."""
    a, op, b = ss[f"{k}_qa"], ss[f"{k}_qop"], ss[f"{k}_qb"]
    if not a or not b:
        return
    template, fmt = pivot.QUICK_OPS[op]
    rb = (f"{ss[f'{k}_qn']:g}" if b[0] == "num" else _ref(*b))
    ss[f"{k}_f"] = "=" + template.format(a=_ref(*a), b=rb)
    other = f"{ss[f'{k}_qn']:g}" if b[0] == "num" else b[1]
    if ss.get(f"{k}_auto_name", True):
        ss[f"{k}_name"] = f"{op.replace('A', a[1], 1).replace('B', other, 1)}"[:80]
    if fmt:
        ss[f"{k}_fmt"] = fmt


def _name_typed(k: str):
    ss[f"{k}_auto_name"] = False                             # user typed a name: stop suggesting one


@st.dialog("Edit calculated field", width="large")
def calc_dialog(view, numeric, vid: str | None = None):
    pv = ss.pv
    columns = pivot.formula_columns(numeric)
    cur = next((v for v in pv["values"] if v["id"] == vid), None)
    others = [v for v in pv["values"] if v["id"] != vid]
    k = f"cf_{ss.pv_gen}_{vid or 'new'}"
    if f"{k}_f" not in ss:                                    # first open: fill the boxes
        ss[f"{k}_f"] = cur["formula"] if cur else "="
        ss[f"{k}_name"] = cur["name"] if cur else f"Calculated field {sum('formula' in v for v in pv['values']) + 1}"
        ss[f"{k}_auto_name"] = cur is None
        ss[f"{k}_s"] = cur.get("summarize", "SUM") if cur else "SUM"
        ss[f"{k}_fmt"] = cur.get("format", "number") if cur else "number"
        ss[f"{k}_dec"] = int(cur.get("decimals", 2)) if cur else 2

    st.caption("Do maths between sheet columns ('Sales Q2 FY25') and pivot columns ([Sales Growth Q2 Vs Q1 FY25]), "
               "with any function.")

    # ---- quick builder
    with st.expander("Quick maths: A ⊕ B", expanded=cur is None, icon=":material/calculate:"):
        refs = [("val", v["name"]) for v in others] + [("col", c) for c in numeric]
        label = (lambda o: "A number…" if o[0] == "num" else (f"[{o[1]}]" if o[0] == "val" else o[1]))
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
        st.caption("[Brackets] = a pivot column (already summarised for each row) · plain = a sheet column.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        name = st.text_input("Calculated field name", key=f"{k}_name", on_change=_name_typed, args=(k,))
        formula = st.text_area("Formula", key=f"{k}_f", height=110,
                               placeholder="=('Sales Q2 FY25'/'Sales Q1 FY25')-1")
        st.pills("Operators", OPERATORS, key=f"{k}_op", label_visibility="collapsed",
                 on_change=_insert, args=(f"{k}_f", f"{k}_op", "op"))
        f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
        fn = f1.selectbox("Function", list(FN_HELP), key=f"{k}_fn",
                          format_func=lambda n: f"{n} — {FN_HELP[n].split('→')[-1].strip()}" if "→" in FN_HELP[n] else n)
        f2.button("Insert", key=f"{k}_fnins", on_click=_insert_fn, args=(f"{k}_f", f"{k}_fn"), width="stretch")
        st.caption(FN_HELP[fn])
        c1, c2, c3 = st.columns([1.4, 1, 0.8])
        summarize = c1.selectbox("Summarize by", SUMMARIZE_ALL, key=f"{k}_s",
                                 help="Sheet columns in the formula are summarised this way for every "
                                      "sector/group, then the formula runs (like Sheets). Pivot columns in "
                                      "[brackets] are used as they are. CUSTOM: write summaries yourself, e.g. "
                                      "=SUM('PAT Q2 FY25')/COUNTA('NSE Code').")
        fmt = c2.selectbox("Format", list(pivot.FORMATS), format_func=pivot.FORMATS.get, key=f"{k}_fmt")
        dec = c3.number_input("Decimals", 0, 4, key=f"{k}_dec")
        err, sample = (pivot.check_formula(formula, view, columns, summarize, others, None, name)
                       if formula.strip() not in ("", "=") else
                       ("Type a formula, or use Quick maths / the buttons and lists.", None))
        if err:
            st.markdown(f'<div class="f-err">✕ {html.escape(err)}</div>', unsafe_allow_html=True)
        else:
            ex = sample.dropna()
            first = (f"{ex.iloc[0] * (100 if fmt == 'percent' else 1):,.{dec}f}{'%' if fmt == 'percent' else ''}"
                     if len(ex) else "blank")
            st.markdown(f'<div class="f-ok">✓ Formula works · {len(ex):,} companies have a value · '
                        f'first company: {first}</div>', unsafe_allow_html=True)
    with right:
        t_sheet, t_pivot = st.tabs([f"Sheet columns ({len(columns)})", f"Pivot columns ({len(others)})"])
        with t_sheet:
            q = st.text_input("Search sheet columns", key=f"{k}_q", placeholder="Search, e.g. PAT Q2",
                              label_visibility="collapsed", icon=":material/search:")
            hits = [c for c in columns if _matches(q, c)]
            with st.container(height=250, border=True):
                st.pills("Sheet columns", hits[:300], key=f"{k}_p", label_visibility="collapsed",
                         on_change=_insert, args=(f"{k}_f", f"{k}_p", "col"))
            st.caption(f"{len(hits)} of {len(columns)} · click to add 'column'")
        with t_pivot:
            q = st.text_input("Search pivot columns", key=f"{k}_vq", placeholder="Search, e.g. growth Q2",
                              label_visibility="collapsed", icon=":material/search:")
            hits = [v["name"] for v in others if _matches(q, v["name"])]
            with st.container(height=250, border=True):
                if hits:
                    st.pills("Pivot columns", hits[:300], key=f"{k}_vp", label_visibility="collapsed",
                             on_change=_insert, args=(f"{k}_f", f"{k}_vp", "val"))
                else:
                    st.caption("No pivot columns match.")
            st.caption(f"{len(hits)} of {len(others)} · click to add [column]")

    taken = {v["name"] for v in others}
    problem = ("Give the field a name." if not name.strip() else
               "Another value already uses this name." if name.strip() in taken else err)
    b1, b2, b3 = st.columns([3, 1, 1])
    if problem and not err:
        b1.caption(f"⚠️ {problem}")
    if b2.button("Cancel", width="stretch", key=f"{k}_cancel"):
        st.rerun()
    if b3.button("OK", type="primary", width="stretch", key=f"{k}_ok", disabled=bool(problem)):
        new = pivot.value_defaults({**(cur or {}), "id": vid or pivot.new_id(), "name": name.strip(),
                                    "formula": formula.strip(), "summarize": summarize, "format": fmt,
                                    "decimals": int(dec)})
        new.pop("column", None)
        if cur:
            pv["values"] = [new if v["id"] == vid else v for v in pv["values"]]
            if cur["name"] != new["name"]:
                _rename_refs(cur["name"], new["name"])
        else:
            pv["values"].append(new)
        for key in [x for x in ss.keys() if str(x).startswith(k + "_")]:
            del ss[key]                                      # next open starts fresh
        _bump()
        st.rerun()


# ---------------------------------------------------------------- editor callbacks
def _add_columns(key):
    for c in ss.get(key) or []:
        text = c in pivot.TEXT_FIELDS
        ss.pv["values"].append(pivot.value_defaults({
            "id": pivot.new_id(), "name": f"COUNTA of {c}" if text else c, "column": c,
            "summarize": "COUNTA" if text else "SUM", "decimals": 0 if text else 2}))
    ss[key] = []
    _bump()


def _rename(vid, key):
    name = (ss.get(key) or "").strip()
    if not name or any(v["name"] == name for v in ss.pv["values"] if v["id"] != vid):
        st.toast("That name is empty or already used.", icon="⚠️")
        return
    for v in ss.pv["values"]:
        if v["id"] == vid:
            _rename_refs(v["name"], name)
            v["name"] = name
    _bump()


def _move(vid, step):
    vals = ss.pv["values"]
    i = next(n for n, v in enumerate(vals) if v["id"] == vid)
    if 0 <= i + step < len(vals):
        vals[i], vals[i + step] = vals[i + step], vals[i]
    _bump()


def _remove(vid):
    _delete([vid])


def _add_filter():
    ss.pv["filters"].append({"id": pivot.new_id(), "field": "", "op": ">", "value": ""})


def _drop_filter(fid):
    ss.pv["filters"] = [f for f in ss.pv["filters"] if f.get("id") != fid]


def _switch(numeric):
    if ss.pv_pick == NEW:
        _set_working(pivot.default_layout(numeric), False)
    else:
        _open(ss.pv_pick, numeric)


# ---------------------------------------------------------------- editor panel
def _values_table():
    """Editable table of the pivot columns (only the ones matching the column search):
    rename, Summarize by, Show as, format, decimals; select rows + Delete key to remove."""
    q = ss.get("pv_colq", "")
    base_all = ss.pv_vbase
    base = [v for v in base_all if _matches(q, v["name"])]
    if not base_all:
        st.caption("No values yet — add a column or a calculated field.")
        ss.pv["values"] = []
        return
    if q.strip():
        st.caption(f"Showing {len(base)} of {len(base_all)} columns matching “{q.strip()}”.")
    if not base:
        return
    errors = pivot.compile_values(base_all, ss.pv_columns)[3]
    rows = pd.DataFrame({
        "Field": [("⚠ " if v["id"] in errors else "") + v["name"] for v in base],
        "Summarize by": [v.get("summarize", "SUM") for v in base],
        "Show as": [SHOW_AS_LABEL.get(v.get("show_as", "default"), "Default") for v in base],
        "Format": [pivot.FORMATS.get(v.get("format", "number"), "Number") for v in base],
        "Dec.": [int(v.get("decimals", 2)) for v in base],
        "Source": [v.get("formula") or f"column: {v.get('column')}" for v in base],
    }, index=[v["id"] for v in base])
    edited = st.data_editor(
        rows, key=f"pv_ved_{ss.pv_gen}_{ss.pv_vver}", hide_index=True, num_rows="delete",
        width="stretch", height=min(460, 38 + 35 * len(rows)),
        column_config={
            "Field": st.column_config.TextColumn("Field", width=190, required=True),
            "Summarize by": st.column_config.SelectboxColumn("Summarize by", options=SUMMARIZE_ALL,
                                                             required=True, width=110),
            "Show as": st.column_config.SelectboxColumn("Show as", options=list(SHOW_AS_KEY),
                                                        required=True, width=125),
            "Format": st.column_config.SelectboxColumn("Format", options=list(pivot.FORMATS.values()),
                                                       required=True, width=85),
            "Dec.": st.column_config.NumberColumn("Dec.", min_value=0, max_value=4, step=1, width=50),
            "Source": st.column_config.TextColumn("Formula / column", disabled=True, width="large"),
        },
    )
    bad = [(v["name"], errors[v["id"]]) for v in base if v["id"] in errors]
    if bad:
        st.warning("⚠ " + " · ".join(f"**{html.escape(n)}**: {html.escape(m)}" for n, m in bad[:3])
                   + (f" · and {len(bad) - 3} more" if len(bad) > 3 else ""))

    by_id = {v["id"]: v for v in base}
    fmt_key = {lbl: k for k, lbl in pivot.FORMATS.items()}
    deleted = [vid for vid in by_id if vid not in edited.index]
    if deleted:                                            # Delete key in the table → same undo-able delete
        _delete(deleted)
        st.rerun()
    updated, renames, fixed = {}, [], False
    for vid, r in edited.iterrows():
        v = dict(by_id[vid])
        name = str(r["Field"]).removeprefix("⚠ ").strip() or v["name"]
        if name != v["name"]:
            renames.append((v["name"], name))
        how = r["Summarize by"]
        if how == pivot.CUSTOM and "formula" not in v:
            how, fixed = "SUM", True                       # CUSTOM needs a formula
        if v.get("column") in pivot.TEXT_FIELDS and how not in pivot.TEXT_OK:
            how, fixed = "COUNTA", True                    # text columns can only be counted
        v.update(name=name, summarize=how, show_as=SHOW_AS_KEY.get(r["Show as"], "default"),
                 format=fmt_key.get(r["Format"], "number"),
                 decimals=int(r["Dec."]) if pd.notna(r["Dec."]) else 2)
        updated[vid] = v
    ss.pv["values"] = [updated.get(v["id"], v) for v in base_all]   # columns hidden by the search stay as they are
    names = [v["name"] for v in ss.pv["values"]]
    if len(set(names)) != len(names):
        st.warning("Two values have the same name — rename one so formulas, sorting and filters know which is which.")
    if renames:                                            # keep [formulas], sorting and filters in step
        for old, new in renames:
            _rename_refs(old, new)
        _bump()
        st.rerun()
    if fixed:
        st.toast("CUSTOM needs a formula and text columns can only use COUNTA/COUNTUNIQUE — adjusted.", icon="ℹ️")
        _bump()
        st.rerun()


def editor(view, numeric):
    pv, g = ss.pv, ss.pv_gen
    names = [v["name"] for v in pv["values"]]

    tpl_ok = pivot.quarterly_template(numeric) is not None
    if tpl_ok and st.button("Build quarterly pivot (like your sheet)", icon=":material/auto_awesome:",
                            width="stretch", key=f"pv_tpl_{g}"):
        template_dialog(numeric)

    # ---- Rows
    st.markdown('<div class="pe-h">Rows</div>', unsafe_allow_html=True)
    levels = st.multiselect("Rows (in order)", LEVELS, default=pv["levels"], key=f"pv_lv_{g}",
                            label_visibility="collapsed", placeholder="Pick row levels")
    pv["levels"] = levels or ["Sector"]
    st.markdown('<div class="pe-sub">Order and sort by</div>', unsafe_allow_html=True)
    for level in pv["levels"] + [pivot.COMPANY]:
        cfg = pv["sort"].setdefault(level, {"by": "", "dir": "asc"})
        by_opts = [""] + names
        if cfg.get("by") not in by_opts:
            cfg["by"] = ""
        c1, c2, c3 = st.columns([1.05, 1.65, 1.05], vertical_alignment="center")
        c1.markdown(f'<div class="pe-lvl">{"Company" if level == pivot.COMPANY else level}</div>',
                    unsafe_allow_html=True)
        cfg["by"] = c2.selectbox(f"{level} sort by", by_opts, index=by_opts.index(cfg["by"]),
                                 format_func=lambda x: "Name" if x == "" else x,
                                 key=f"pv_sb_{g}_{level}", label_visibility="collapsed")
        cfg["dir"] = c3.selectbox(f"{level} order", ["asc", "desc"], index=0 if cfg["dir"] == "asc" else 1,
                                  format_func=lambda d: "↑ Asc" if d == "asc" else "↓ Desc",
                                  key=f"pv_sd_{g}_{level}", label_visibility="collapsed")
    pv["grand_total"] = st.checkbox("Show grand total", value=pv.get("grand_total", True), key=f"pv_gt_{g}")

    # ---- Values
    st.markdown('<div class="pe-h" style="margin-top:12px">Values</div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns([1, 1.1, 0.9])
    with a1.popover("Add", icon=":material/add:", width="stretch"):
        used = {v.get("column") for v in pv["values"]}
        choices = [c for c in numeric if c not in used] + [c for c in pivot.TEXT_FIELDS
                                                           if c in view.columns and c not in used]
        st.multiselect("Columns", choices, key=f"pv_add_{g}", placeholder="Search columns",
                       help="Number columns are added with SUM; text columns (NSE Code…) with COUNTA.")
        st.button("Add", type="primary", on_click=_add_columns, args=(f"pv_add_{g}",), width="stretch")
    if a2.button("Calculated field", icon=":material/function:", width="stretch", key=f"pv_cf_{g}"):
        calc_dialog(view, numeric)
    with a3.popover("Edit", icon=":material/edit:", width="stretch", disabled=not pv["values"]):
        ids = [v["id"] for v in pv["values"]]
        vid = st.selectbox("Value", ids, key=f"pv_pick_{g}_{ss.pv_vver}",
                           format_func=lambda i: next(v["name"] for v in pv["values"] if v["id"] == i))
        v = next((x for x in pv["values"] if x["id"] == vid), None)
        if v:
            new_name = st.text_input("Name", value=v["name"], key=f"pv_rn_{g}_{vid}_{ss.pv_vver}")
            r1, r2 = st.columns(2)
            r1.button("Rename", width="stretch", on_click=_rename, args=(vid, f"pv_rn_{g}_{vid}_{ss.pv_vver}"),
                      disabled=new_name.strip() in ("", v["name"]), key=f"pv_rnb_{g}")
            if "formula" in v and r2.button("Edit formula", icon=":material/function:", width="stretch",
                                            key=f"pv_openfx_{g}"):
                calc_dialog(view, numeric, vid)
            m1, m2, m3 = st.columns(3)
            pos = ids.index(vid)
            m1.button("Left", icon=":material/arrow_back:", width="stretch", on_click=_move, args=(vid, -1),
                      disabled=pos == 0, key=f"pv_ml_{g}", help="Move one column left")
            m2.button("Right", icon=":material/arrow_forward:", width="stretch", on_click=_move, args=(vid, 1),
                      disabled=pos == len(ids) - 1, key=f"pv_mr_{g}", help="Move one column right")
            m3.button("Remove", icon=":material/delete:", width="stretch", on_click=_remove, args=(vid,),
                      key=f"pv_rm_{g}")
    _values_table()
    st.caption("Change Summarize by / Show as / Format / decimals right in the table · select rows and "
               "press Delete to remove · use **Edit** to rename, move or change a formula.")

    # ---- Filters
    st.markdown('<div class="pe-h" style="margin-top:12px">Filters</div>', unsafe_allow_html=True)
    fields = [c for c in pivot.TEXT_FIELDS if c in view.columns] + numeric + \
             [v["name"] for v in pv["values"] if "formula" in v]
    for f in pv["filters"]:
        f.setdefault("id", pivot.new_id())
        c1, c2, c3, c4 = st.columns([1.6, 0.95, 1.1, 0.35], vertical_alignment="center")
        f["field"] = c1.selectbox("Field", [""] + fields, index=([""] + fields).index(f["field"])
                                  if f.get("field") in fields else 0, key=f"pv_ff_{g}_{f['id']}",
                                  label_visibility="collapsed", format_func=lambda x: x or "Pick a field")
        f["op"] = c2.selectbox("Condition", pivot.FILTER_OPS, key=f"pv_fo_{g}_{f['id']}",
                               index=pivot.FILTER_OPS.index(f["op"]) if f.get("op") in pivot.FILTER_OPS else 0,
                               label_visibility="collapsed")
        f["value"] = c3.text_input("Value", value=str(f.get("value", "")), key=f"pv_fv_{g}_{f['id']}",
                                   label_visibility="collapsed",
                                   placeholder="e.g. 0" if f["op"] != "between" else "e.g. 0, 10",
                                   disabled=f["op"] in ("is empty", "is not empty"))
        c4.button("", icon=":material/close:", key=f"pv_fx_{g}_{f['id']}", type="tertiary",
                  on_click=_drop_filter, args=(f["id"],), help="Remove filter")
    st.button("Add filter", icon=":material/filter_alt:", on_click=_add_filter, key=f"pv_fa_{g}")


# ---------------------------------------------------------------- the table
@st.cache_data(ttl=600, max_entries=40, show_spinner=False)
def _pivot_page(view, layout_json: str, columns: tuple, height: int, show_json: str = "") -> str:
    """Built once per filter + layout + column search; switching back and forth is instant."""
    show = json.loads(show_json) if show_json else None
    return ui.pivot_html(pivot.build_tree(view, json.loads(layout_json), list(columns), show), height)


_CSS = """<style>
.st-key-colbar { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:14px; padding:10px 14px 12px;
                 margin-bottom:10px; }
.st-key-colbar [data-testid="stWidgetLabel"] { display:none; }
.stApp [data-testid="stExpander"] details { border-radius:12px; border-color:#E5E7EB; }
</style>"""


def render() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    ctx = st.session_state["ctx"]
    view, df, numeric = ctx["view"], ctx["df"], ctx["numeric"]
    _init(numeric)
    ss.pv_columns = pivot.formula_columns(numeric)

    ui.stat_strip(view, df)

    # ---- layout bar
    with st.container(key="pvbar"):
        c = st.columns([2.2, 1.4, 0.85, 0.95, 0.85, 1.25], vertical_alignment="bottom")
        options = list(ss.pv_layouts) + ([] if _is_saved() else [ss.pv["name"]]) + [NEW]
        ss.pv_pick = ss.pv["name"]
        c[0].selectbox("Layout", options, key="pv_pick", on_change=_switch, args=(numeric,),
                       format_func=lambda n: n if n in ss.pv_layouts or n == NEW else f"{n} (not saved)")
        status_slot = c[1].empty()
        save_clicked = c[2].button("Save", icon=":material/save:", type="primary", width="stretch",
                                   help=f"Saved to {storage.where()}", key="pv_save")
        if c[3].button("Save as", icon=":material/save_as:", width="stretch"):
            save_as_dialog()
        if c[4].button("Delete", icon=":material/delete:", width="stretch", disabled=not _is_saved()):
            delete_dialog(numeric)
        c[5].toggle("Pivot editor", key="pv_open", value=True)

    if view.empty:
        st.warning("No companies match these filters.")
        return

    if ss.pv_open:
        main, side = st.columns([2.25, 1.75], gap="medium")
        with side.container(key="pveditor"):
            st.markdown('<div class="pe-title">Pivot table editor</div>', unsafe_allow_html=True)
            editor(view, numeric)
    else:
        main = st.container()

    # save / status after the editor has applied this run's changes
    if save_clicked:
        if _is_saved():
            if _save(ss.pv["name"]):
                st.toast(f"Saved “{ss.pv['name']}”", icon="✅")
        else:
            save_as_dialog()
    status = ("● Unsaved changes" if _dirty() and _is_saved() else
              "● Not saved yet" if not _is_saved() else "✓ Saved")
    status_slot.markdown(f'<div class="pv-status {"ok" if not _dirty() else "warn"}">{status}</div>',
                         unsafe_allow_html=True)

    with main:
        pv = ss.pv
        if not pv["values"] and not ss.get("pv_undo"):
            st.info("Add at least one value in the pivot editor.")
            return

        # ---- column bar: search columns · delete columns · undo
        with st.container(key="colbar"):
            c1, c2, c3 = st.columns([3.2, 1.3, 1], vertical_alignment="bottom")
            q = c1.text_input("Search columns", key="pv_colq", on_change=_bump, icon=":material/search:",
                              placeholder="Show only columns matching… e.g. PAT Q2  (comma = or: PAT, OPM)")
            shown = [v for v in pv["values"] if _matches(q, v["name"])]
            with c2.popover("Delete columns", icon=":material/delete:", width="stretch", disabled=not shown):
                names = {v["id"]: v["name"] for v in shown}
                pick = st.multiselect("Columns to delete", list(names), format_func=names.get,
                                      key=f"pv_delpick_{ss.pv_gen}_{ss.pv_vver}", placeholder="Pick columns")
                users = _users_of(set(pick))
                if users:
                    st.warning("Used in the formula of: " + ", ".join(users[:5])
                               + (" …" if len(users) > 5 else "") + " — those will show blank.")
                st.button(f"Delete {len(pick)} selected" if pick else "Delete selected", type="primary",
                          disabled=not pick, on_click=_delete, args=(pick,), width="stretch", key="pv_delsel")
                if q.strip():
                    st.button(f"Delete all {len(shown)} matching “{q.strip()}”", on_click=_delete,
                              args=([v["id"] for v in shown],), width="stretch", key="pv_delall")
                st.caption("You can undo a delete. Nothing is permanent until you press Save.")
            c3.button("Undo delete", icon=":material/undo:", on_click=_undo, width="stretch",
                      disabled=not ss.get("pv_undo"), key="pv_undo_btn")
            if q.strip():
                st.caption(f"Showing **{len(shown)}** of {len(pv['values'])} columns · clear the search to see all")

        if not pv["values"]:
            st.info("All columns deleted — press **Undo delete**, or add values in the pivot editor.")
            return
        if not shown:
            st.info(f"No column matches “{q.strip()}”.")
            return
        n_f = sum(1 for f in pv["filters"] if f.get("field"))
        ui.section(" › ".join(pv["levels"] + ["Company"]),
                   (f"{n_f} filter{'s' if n_f > 1 else ''} on · " if n_f else "")
                   + "Green = above 0, red = below 0")
        layout_json = json.dumps({k: pv.get(k) for k in ("levels", "values", "filters", "sort", "grand_total")})
        show_json = json.dumps([v["id"] for v in shown]) if len(shown) != len(pv["values"]) else ""
        cols = list(dict.fromkeys([c for c in ui.TREE_COLS if c in view.columns] + numeric))
        page = _pivot_page(view[cols], layout_json, tuple(ss.pv_columns), 640, show_json)
        if hasattr(st, "iframe"):                       # newer Streamlit: grows/shrinks with the table
            st.iframe(page, height="content")
        else:                                           # older Streamlit
            import streamlit.components.v1 as components
            components.html(page, height=704)