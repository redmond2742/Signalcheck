"""
tools/_template_tool.py  --  Starting point for a new SignalCheck tool.

HOW TO ADD A TOOL
=================
1. Copy this file to  tools/your_tool.py  and rename things.
2. Build your UI below (it's a normal Streamlit script).
   - Do NOT call st.set_page_config — the suite entry point (app.py) does that.
   - Put any controls you want in the left sidebar inside `with st.sidebar:`.
   - Namespace any st.session_state keys with a unique prefix (see STATE_KEY)
     so tools don't clobber each other's state.
3. Register it in  tool_registry.py  by adding an entry to TOOLS:

       {
           "key": "yourtool",
           "title": "Your Tool Name",
           "icon": "🧰",
           "page": "tools/your_tool.py",
           "tagline": "One short line describing what it does.",
           "status": "live",      # or "soon" to show it as Coming soon
       }

That's all — it now appears on the home page and in the sidebar.

Put any reusable analysis logic in its own module (like flash_check.py) and
import it here, so the same engine can be used from a CLI too.
"""

import streamlit as st

STATE_KEY = "template_state"  # change to something unique per tool

st.title("🧰 Template Tool")
st.caption("Replace this with your tool. See the docstring at the top of this file.")

with st.sidebar:
    st.header("Settings")
    st.text_input("Example setting", value="")

uploads = st.file_uploader("Upload file(s)", accept_multiple_files=True)
if uploads:
    st.success(f"Received {len(uploads)} file(s). Add your processing here.")
