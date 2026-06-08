#!/usr/bin/env python3
"""
app.py  --  SignalCheck suite entry point.

This is the file to run:
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501

It builds a Home page plus one navigation entry per tool listed in
tool_registry.py. Adding a tool there makes it show up here automatically.
"""

import streamlit as st

from tool_registry import SUITE_NAME, SUITE_ICON, live_tools

# set_page_config is called once, here in the entry script (pages must not call it).
st.set_page_config(page_title=SUITE_NAME, page_icon=SUITE_ICON, layout="wide")

# Build the navigation: Home first, then one page per live tool.
pages = [st.Page("home.py", title="Home", icon="🏠", default=True)]
for tool in live_tools():
    pages.append(st.Page(tool["page"], title=tool["title"], icon=tool["icon"]))

st.navigation(pages).run()
