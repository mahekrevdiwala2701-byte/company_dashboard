"""
Sector Rotation – Results Basis

Files
  app.py              entry point: loads data, draws the filter bar, top navigation
  data.py             Google Sheets loading, cleaning, Sector › Industry › Group › Sub group mapping
  ui.py               design (CSS) and reusable pieces: filter bar, stat strip, expandable table
  dashboard.py        main page: expandable Sector › Industry Group › Company table
  all_data.py         every company and column, sortable, CSV download

Run:  streamlit run app.py
"""

import streamlit as st

import ui
from data import DataError, get_data

try:                                    # page files next to app.py …
    import all_data
    import dashboard
except ModuleNotFoundError:             # … or inside a "views" folder — both work
    from views import all_data, dashboard

st.set_page_config(page_title="Sector Rotation", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")
ui.inject_css()

try:
    df, numeric = get_data()
except DataError as e:
    st.error(str(e))
    st.info("Share both sheets as **Anyone with the link → Viewer**, then press ↻.")
    st.stop()

nav = st.navigation(
    [
        st.Page(dashboard.render, title="Dashboard", icon="📈", url_path="dashboard", default=True),
        st.Page(all_data.render, title="All data", icon="🗂️", url_path="all-data"),
    ],
    position="top",
)

TITLES = {
    "Dashboard": ("Results basis", "Sector Rotation",
                  "Open a sector to see its industry groups, then the companies inside."),
    "All data": ("Results basis", "All companies",
                 "Every company and every column from the results sheet."),
}
ui.page_title(*TITLES.get(nav.title, TITLES["Dashboard"]))

# filters are drawn here (not inside a page) so they stay set when you switch pages
view = ui.filter_bar(df)
st.session_state["ctx"] = {"df": df, "view": view, "numeric": numeric}
nav.run()