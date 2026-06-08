#!/usr/bin/env python3
"""
flash_app.py  --  Backward-compatible launcher for the 4-Way Flash Checker only.

The full suite now lives in app.py (run that to get the SignalCheck home page
and all tools).  This shim still works if you prefer to launch the flash
checker on its own:

    streamlit run flash_app.py
"""

import streamlit as st

st.set_page_config(page_title="4-Way Flash Checker", page_icon="🚦", layout="wide")

# Running the tool's page script renders its UI (set_page_config handled above).
import tools.flash_check_tool  # noqa: E402,F401
