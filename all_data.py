"""Every company and every column, colour-coded, sortable, downloadable."""

import streamlit as st
import ui
from data import LEVELS


def render() -> None:
    ctx = st.session_state["ctx"]
    view, numeric = ctx["view"], ctx["numeric"]

    if view.empty:
        st.warning("No companies match these filters.")
        return

    front = [c for c in ["Name", "BSE Code", "NSE Code"] + LEVELS if c in view.columns]
    rest = [c for c in view.columns if c not in front and not c.startswith("_")]
    table = view[front + rest]

    c1, c2, c3 = st.columns([2, 3, 1])
    sort_options = ["(sheet order)"] + numeric + [c for c in ["Name", "Sector"] if c in table.columns]
    sort_by = c1.selectbox("Sort by", sort_options, key="a_sort")
    hide = c2.multiselect("Hide columns", [c for c in table.columns if c != "Name"], key="a_hide",
                          placeholder="Showing all columns")
    c3.markdown('<div style="height:1.9rem"></div>', unsafe_allow_html=True)
    colour = c3.toggle("Colour cells", value=True, key="a_colour")

    t = table.drop(columns=hide)
    if sort_by != "(sheet order)":
        t = t.sort_values(sort_by, ascending=sort_by in ("Name", "Sector"), na_position="last")
    nums = [c for c in numeric if c in t.columns]

    cfg = {c: st.column_config.NumberColumn(c, format="%.2f") for c in nums}
    if "Name" in t.columns:
        cfg["Name"] = st.column_config.TextColumn("Name", pinned=True)
    MAX_COLOURED_CELLS = 15_000                     # colouring is slow; only do it for smaller views
    too_big = len(t) * max(1, len(nums)) > MAX_COLOURED_CELLS
    data = ui.styled(t, nums) if colour and not too_big else t

    ui.section(f"{len(t):,} companies", f"{len(t.columns)} columns · click a header to sort")
    st.dataframe(data, width="stretch", hide_index=True, height=680, column_config=cfg)
    if colour and too_big:
        st.caption("Cell colours switch on automatically when you filter down to fewer companies "
                   "(keeps this page fast).")
    st.download_button("⬇ Download CSV", t.to_csv(index=False), "sector_rotation.csv", "text/csv")