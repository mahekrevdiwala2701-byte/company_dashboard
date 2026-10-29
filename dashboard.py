"""Main page: expandable pivot (Sector › Industry Group › Company) + a Google-Sheets-style pivot editor.

Pivot editor
  Rows    – which levels, in which order, and how each level is sorted (name or any value, A→Z / Z→A)
  Values  – columns from the sheet or calculated fields, each with "Summarize by"
  Layouts – save / save as / open / delete (stored by storage.py)
"""

import copy
import html
import json

import streamlit as st

import pivot
import storage
import ui
from data import LEVELS

ss = st.session_state
SUMMARIZE_LABELS = {**{s: s for s in pivot.SUMMARIZE},
                    pivot.CUSTOM: "CUSTOM (formula on group totals)"}
NEW = "＋ New layout"


# ---------------------------------------------------------------- state
def _snapshot(layout: dict) -> str:
    return json.dumps({k: layout.get(k) for k in ("levels", "values", "sort")}, sort_keys=True)


def _open(name: str, numeric: list[str]) -> None:
    """Make `name` the working layout (a copy — nothing is saved until you press Save)."""
    saved = ss.pv_layouts.get(name)
    lay = pivot.clean_layout(copy.deepcopy(saved), numeric) if saved else pivot.default_layout(numeric)
    lay["name"] = name if saved else "Default"
    ss.pv = lay
    ss.pv_saved = _snapshot(lay) if saved else ""
    ss.pv_gen = ss.get("pv_gen", 0) + 1          # fresh widget keys for the new layout


def _init(numeric: list[str]) -> None:
    if "pv_layouts" not in ss:
        ss.pv_layouts = storage.load_all()
    if "pv" not in ss:
        _open(next(iter(ss.pv_layouts), "Default"), numeric)


def _is_saved() -> bool:
    return ss.pv["name"] in ss.pv_layouts


def _dirty() -> bool:
    return not _is_saved() or _snapshot(ss.pv) != ss.pv_saved


def _save(name: str) -> bool:
    lay = copy.deepcopy(ss.pv)
    lay["name"] = name
    layouts = {**ss.pv_layouts, name: lay}
    if storage.save_all(layouts):
        ss.pv_layouts = layouts
        ss.pv["name"] = name
        ss.pv_saved = _snapshot(ss.pv)
        return True
    return False


# ---------------------------------------------------------------- dialogs
@st.dialog("Save layout as")
def save_as_dialog():
    name = st.text_input("Layout name", value="" if ss.pv["name"] == "Default" else f'{ss.pv["name"]} copy',
                         placeholder="e.g. Q2 FY25 results", max_chars=60)
    exists = name.strip() in ss.pv_layouts
    if exists:
        st.warning("A layout with this name exists — saving will replace it.")
    st.caption(f"Saved to {storage.where()}.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button("Replace" if exists else "Save", type="primary", width="stretch",
                 disabled=not name.strip()):
        if _save(name.strip()):
            st.toast(f"Saved “{name.strip()}”", icon="✅")
            st.rerun()


@st.dialog("Delete layout")
def delete_dialog(numeric):
    name = ss.pv["name"]
    st.write(f"Delete **{name}**? This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button("Delete", type="primary", width="stretch"):
        layouts = {k: v for k, v in ss.pv_layouts.items() if k != name}
        if storage.save_all(layouts):
            ss.pv_layouts = layouts
            _open(next(iter(layouts), "Default"), numeric)
            st.toast(f"Deleted “{name}”", icon="🗑️")
            st.rerun()


def _insert_column(fkey: str, pkey: str):
    col = ss.get(pkey)
    if col:
        text = ss.get(fkey, "") or "="
        sep = "" if text.endswith(("=", "(", " ", "+", "-", "*", "/", ",")) else " "
        ss[fkey] = f"{text}{sep}'{col}'"
        ss[pkey] = None


@st.dialog("Edit calculated field", width="large")
def calc_dialog(view, numeric, vid: str | None = None):
    pv = ss.pv
    cur = next((v for v in pv["values"] if v["id"] == vid), None)
    k = f"cf_{ss.pv_gen}_{vid or 'new'}"
    st.caption("Calculated fields let you add custom calculations of columns to your pivot table.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        name = st.text_input("Calculated field name", key=f"{k}_name",
                             value=cur["name"] if cur else f"Calculated field {sum('formula' in v for v in pv['values']) + 1}")
        if f"{k}_f" not in ss:
            ss[f"{k}_f"] = cur["formula"] if cur else "="
        formula = st.text_area("Formula", key=f"{k}_f", height=140,
                               placeholder="=('Sales Q2 FY25'/'Sales Q1 FY25')-1")
        err, sample = pivot.check_formula(formula, view, numeric) if formula.strip() not in ("", "=") \
            else ("Type a formula, or click a column on the right to add it.", None)
        c1, c2 = st.columns(2)
        opts = pivot.SUMMARIZE + [pivot.CUSTOM]
        summarize = c1.selectbox("Summarize by", opts, format_func=SUMMARIZE_LABELS.get, key=f"{k}_s",
                                 index=opts.index(cur["summarize"]) if cur and cur.get("summarize") in opts else 0,
                                 help="SUM/AVERAGE/…: the formula is worked out for every company, then "
                                      "summarised for each sector/group. CUSTOM: the formula is applied to "
                                      "each group's totals, e.g. (total Q2 sales ÷ total Q1 sales) − 1.")
        fmts = list(pivot.FORMATS)
        fmt = c2.selectbox("Show as", fmts, format_func=pivot.FORMATS.get, key=f"{k}_fmt",
                           index=fmts.index(cur.get("format", "number")) if cur else 0)
        if err:
            st.markdown(f'<div class="f-err">✕ {html.escape(err)}</div>', unsafe_allow_html=True)
        else:
            ex = sample.dropna()
            shown = (f"{ex.iloc[0] * (100 if fmt == 'percent' else 1):,.2f}{'%' if fmt == 'percent' else ''}"
                     if len(ex) else "blank")
            st.markdown(f'<div class="f-ok">✓ Formula works · {len(ex):,} companies have a value · '
                        f'first: {shown}</div>', unsafe_allow_html=True)
    with right:
        st.markdown("**Columns** · click to add to the formula")
        q = st.text_input("Search columns", key=f"{k}_q", placeholder="Search",
                          label_visibility="collapsed", icon=":material/search:").lower()
        matches = [c for c in numeric if q in c.lower()]
        with st.container(height=230, border=True):
            st.pills("Columns", matches[:200], key=f"{k}_p", label_visibility="collapsed",
                     on_change=_insert_column, args=(f"{k}_f", f"{k}_p"))
        st.caption("Functions: ABS, ROUND, MIN, MAX, SQRT, IF, IFERROR · operators + − * / ^ ( )")

    taken = {v["name"] for v in pv["values"] if v["id"] != vid}
    problem = ("Give the field a name." if not name.strip() else
               "Another value already uses this name." if name.strip() in taken else err)
    b1, b2, b3 = st.columns([3, 1, 1])
    if problem and not err:
        b1.caption(f"⚠️ {problem}")
    if b2.button("Cancel", width="stretch", key=f"{k}_cancel"):
        st.rerun()
    if b3.button("OK", type="primary", width="stretch", key=f"{k}_ok", disabled=bool(problem)):
        new = {"id": vid or pivot.new_id(), "name": name.strip(), "formula": formula.strip(),
               "summarize": summarize, "format": fmt}
        if cur:
            old = cur["name"]
            pv["values"] = [new if v["id"] == vid else v for v in pv["values"]]
            for cfg in pv["sort"].values():              # keep sorting pointed at the renamed field
                if cfg.get("by") == old:
                    cfg["by"] = new["name"]
        else:
            pv["values"].append(new)
        st.rerun()


# ---------------------------------------------------------------- editor callbacks
def _remove(vid):
    gone = next(v["name"] for v in ss.pv["values"] if v["id"] == vid)
    ss.pv["values"] = [v for v in ss.pv["values"] if v["id"] != vid]
    for cfg in ss.pv["sort"].values():
        if cfg.get("by") == gone:
            cfg["by"] = ""


def _move(vid, step):
    vals = ss.pv["values"]
    i = next(n for n, v in enumerate(vals) if v["id"] == vid)
    j = i + step
    if 0 <= j < len(vals):
        vals[i], vals[j] = vals[j], vals[i]


def _add_columns(key):
    for c in ss.get(key) or []:
        ss.pv["values"].append({"id": pivot.new_id(), "name": c, "column": c,
                                "summarize": "AVERAGE", "format": "number"})
    ss[key] = []


def _switch(numeric):
    choice = ss.pv_pick
    if choice == NEW:
        ss.pv = pivot.default_layout(numeric)
        ss.pv_saved = ""
        ss.pv_gen += 1
    else:
        _open(choice, numeric)


# ---------------------------------------------------------------- editor panel
def editor(view, numeric):
    pv, g = ss.pv, ss.pv_gen
    names = [v["name"] for v in pv["values"]]

    st.markdown('<div class="pe-h">Rows</div>', unsafe_allow_html=True)
    levels = st.multiselect("Rows (in order)", LEVELS, default=pv["levels"], key=f"pv_lv_{g}",
                            label_visibility="collapsed", placeholder="Pick row levels")
    pv["levels"] = levels or ["Sector"]

    st.markdown('<div class="pe-sub">Sort order</div>', unsafe_allow_html=True)
    for level in pv["levels"] + [pivot.COMPANY]:
        cfg = pv["sort"].setdefault(level, {"by": "", "dir": "asc"})
        by_opts = [""] + names
        if cfg.get("by") not in by_opts:
            cfg["by"] = ""
        c1, c2, c3 = st.columns([1.1, 1.6, 1.05], vertical_alignment="center")
        c1.markdown(f'<div class="pe-lvl">{"Company" if level == pivot.COMPANY else level}</div>',
                    unsafe_allow_html=True)
        cfg["by"] = c2.selectbox(f"{level} sort by", by_opts, index=by_opts.index(cfg["by"]),
                                 format_func=lambda x: "Name" if x == "" else x,
                                 key=f"pv_sb_{g}_{level}", label_visibility="collapsed")
        cfg["dir"] = c3.selectbox(f"{level} order", ["asc", "desc"], index=0 if cfg["dir"] == "asc" else 1,
                                  format_func=lambda d: "↑ Asc" if d == "asc" else "↓ Desc",
                                  key=f"pv_sd_{g}_{level}", label_visibility="collapsed")

    st.markdown('<div class="pe-h" style="margin-top:14px">Values</div>', unsafe_allow_html=True)
    a1, a2 = st.columns(2)
    with a1.popover("Add column", icon=":material/add:", width="stretch"):
        unused = [c for c in numeric if c not in {v.get("column") for v in pv["values"]}]
        st.multiselect("Columns", unused, key=f"pv_add_{g}", placeholder="Search columns")
        st.button("Add", type="primary", on_click=_add_columns, args=(f"pv_add_{g}",), width="stretch")
    if a2.button("Calculated field", icon=":material/function:", width="stretch", key=f"pv_cf_{g}"):
        calc_dialog(view, numeric)

    if not pv["values"]:
        st.caption("No values yet — add a column or a calculated field.")
    with st.container(height=min(560, 40 + 150 * max(1, len(pv["values"]))), border=False):
        for n, v in enumerate(pv["values"]):
            with st.container(border=True, key=f"pvcard_{g}_{v['id']}"):
                h1, h2 = st.columns([5, 3], vertical_alignment="center")
                badge = '<span class="pe-fx">fx</span>' if "formula" in v else ""
                h1.markdown(f'<div class="pe-name" title="{html.escape(v["name"])}">{badge}{html.escape(v["name"])}</div>',
                            unsafe_allow_html=True)
                with h2:
                    b = st.columns(4 if "formula" in v else 3, gap="small")
                    b[0].button("", icon=":material/arrow_upward:", key=f"up_{g}_{v['id']}", help="Move left",
                                on_click=_move, args=(v["id"], -1), disabled=n == 0, type="tertiary")
                    b[1].button("", icon=":material/arrow_downward:", key=f"dn_{g}_{v['id']}", help="Move right",
                                on_click=_move, args=(v["id"], 1), disabled=n == len(pv["values"]) - 1,
                                type="tertiary")
                    if "formula" in v and b[2].button("", icon=":material/edit:", key=f"ed_{g}_{v['id']}",
                                                      help="Edit formula", type="tertiary"):
                        calc_dialog(view, numeric, v["id"])
                    b[-1].button("", icon=":material/close:", key=f"rm_{g}_{v['id']}", help="Remove",
                                 on_click=_remove, args=(v["id"],), type="tertiary")
                if "formula" in v:
                    st.markdown(f'<div class="pe-formula">{html.escape(v["formula"])}</div>', unsafe_allow_html=True)
                s1, s2 = st.columns(2)
                opts = pivot.SUMMARIZE + ([pivot.CUSTOM] if "formula" in v else [])
                v["summarize"] = s1.selectbox("Summarize by", opts, format_func=lambda x: x.title() if x != pivot.CUSTOM else "Custom",
                                              index=opts.index(v["summarize"]) if v["summarize"] in opts else 1,
                                              key=f"pv_s_{g}_{v['id']}")
                fmts = list(pivot.FORMATS)
                v["format"] = s2.selectbox("Show as", fmts, format_func=lambda x: "Percent" if x == "percent" else "Number",
                                           index=fmts.index(v.get("format", "number")), key=f"pv_f_{g}_{v['id']}")


# ---------------------------------------------------------------- the table
@st.cache_data(ttl=600, max_entries=40, show_spinner=False)
def _pivot_page(view, layout_json: str, columns: tuple, height: int) -> str:
    """Built once per filter + layout; switching back and forth is instant."""
    return ui.pivot_html(pivot.build_tree(view, json.loads(layout_json), list(columns)), height)


def render() -> None:
    ctx = st.session_state["ctx"]
    view, df, numeric = ctx["view"], ctx["df"], ctx["numeric"]
    _init(numeric)
    pv = ss.pv

    ui.stat_strip(view, df)

    # ---- layout bar
    with st.container(key="pvbar"):
        c = st.columns([2.2, 1.4, 0.85, 0.95, 0.85, 1.25], vertical_alignment="bottom")
        options = list(ss.pv_layouts) + ([] if _is_saved() else [pv["name"]]) + [NEW]
        ss.pv_pick = pv["name"]
        c[0].selectbox("Layout", options, key="pv_pick", on_change=_switch, args=(numeric,),
                       format_func=lambda n: n if n in ss.pv_layouts or n == NEW else f"{n} (not saved)")
        status = ("● Unsaved changes" if _dirty() and _is_saved() else
                  "● Not saved yet" if not _is_saved() else "✓ Saved")
        c[1].markdown(f'<div class="pv-status {"ok" if not _dirty() else "warn"}">{status}</div>',
                      unsafe_allow_html=True)
        if c[2].button("Save", icon=":material/save:", type="primary", width="stretch",
                       disabled=not _dirty(), help=f"Saved to {storage.where()}"):
            if _is_saved():
                if _save(pv["name"]):
                    st.toast(f"Saved “{pv['name']}”", icon="✅")
                    st.rerun()
            else:
                save_as_dialog()
        if c[3].button("Save as", icon=":material/save_as:", width="stretch"):
            save_as_dialog()
        if c[4].button("Delete", icon=":material/delete:", width="stretch", disabled=not _is_saved()):
            delete_dialog(numeric)
        c[5].toggle("Pivot editor", key="pv_open", value=True)

    if view.empty:
        st.warning("No companies match these filters.")
        return

    if ss.pv_open:
        main, side = st.columns([2.7, 1.25], gap="medium")
        with side.container(key="pveditor"):
            st.markdown('<div class="pe-title">Pivot table editor</div>', unsafe_allow_html=True)
            editor(view, numeric)
    else:
        main = st.container()

    with main:
        pv = ss.pv
        if not pv["values"]:
            st.info("Add at least one value in the pivot editor.")
            return
        ui.section(" › ".join(pv["levels"] + ["Company"]),
                   "Green = above 0, red = below 0 · columns that are never negative are left plain")
        layout_json = json.dumps({k: pv[k] for k in ("levels", "values", "sort")})
        cols = [c for c in ui.TREE_COLS if c in view.columns] + numeric
        page = _pivot_page(view[cols], layout_json, tuple(numeric), 640)
        if hasattr(st, "iframe"):                       # newer Streamlit: grows/shrinks with the table
            st.iframe(page, height="content")
        else:                                           # older Streamlit
            import streamlit.components.v1 as components
            components.html(page, height=704)