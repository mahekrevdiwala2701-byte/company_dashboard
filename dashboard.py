"""Main page: expandable Sector › Industry Group › Company table (like a Google Sheets pivot)."""

import streamlit as st
import ui
from data import LEVELS


@st.cache_data(ttl=600, max_entries=40, show_spinner=False)
def _pivot_page(view, levels: tuple, metrics: tuple, how: str, height: int) -> str:
    """Builds the expandable table once per filter/column choice; repeat clicks are instant."""
    return ui.pivot_html(ui.build_tree(view, list(levels), list(metrics), how), height)


def render() -> None:
    ctx = st.session_state["ctx"]
    view, df, numeric = ctx["view"], ctx["df"], ctx["numeric"]

    ui.stat_strip(view, df)

    if view.empty:
        st.warning("No companies match these filters.")
        return
    if not numeric:
        st.info("The results sheet has no number columns to show.")
        return

    c1, c2, c3 = st.columns([2.2, 1, 3])
    levels = c1.pills("Drill down by", LEVELS, selection_mode="multi",
                      default=["Sector", "Industry Group"], key="d_levels",
                      help="Pick the levels to open, in order. Companies are always the last level.")
    levels = [lv for lv in LEVELS if lv in (levels or [])] or ["Sector"]
    how = c2.segmented_control("Group rows show", ["Average", "Median"], default="Average",
                               key="d_how") or "Average"
    metrics = c3.multiselect("Columns", numeric, default=numeric, key="d_metrics",
                             placeholder="Pick the columns to show")
    if not metrics:
        st.info("Pick at least one column.")
        return

    ui.section(" › ".join(levels + ["Company"]),
               "Green = above 0, red = below 0 · columns that are never negative (e.g. price) are left plain")
    HEIGHT = 680                                    # table scrolls inside beyond this
    cols = [c for c in ui.TREE_COLS if c in view.columns] + list(metrics)
    page = _pivot_page(view[cols], tuple(levels), tuple(metrics), how, HEIGHT)
    if hasattr(st, "iframe"):                       # newer Streamlit: grows/shrinks with the table
        st.iframe(page, height="content")
    else:                                           # older Streamlit
        import streamlit.components.v1 as components
        components.html(page, height=HEIGHT + 64)