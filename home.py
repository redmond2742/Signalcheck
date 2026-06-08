"""
home.py  --  SignalCheck landing page.

Renders a hero header and a card for every tool in tool_registry.py.
This page is data-driven: it never needs editing when you add a tool.
"""

import streamlit as st

from tool_registry import SUITE_NAME, SUITE_ICON, SUITE_TAGLINE, SUITE_BLURB, TOOLS

# ---- Hero -------------------------------------------------------------------
st.markdown(
    f"""
    <div style="padding: 1.6rem 0 0.4rem 0;">
      <div style="font-size: 3.0rem; font-weight: 800; line-height: 1.05;">
        {SUITE_ICON} {SUITE_NAME}
      </div>
      <div style="font-size: 1.35rem; color: #d9534f; font-weight: 600; margin-top: 0.2rem;">
        {SUITE_TAGLINE}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write(SUITE_BLURB)
st.divider()

# ---- Tool cards -------------------------------------------------------------
st.markdown("### Tools")

live = [t for t in TOOLS if t.get("status", "live") == "live"]
soon = [t for t in TOOLS if t.get("status", "live") != "live"]

cols = st.columns(2, gap="large")
for i, tool in enumerate(TOOLS):
    with cols[i % 2]:
        with st.container(border=True):
            st.markdown(f"#### {tool['icon']} {tool['title']}")
            st.write(tool["tagline"])
            if tool.get("status", "live") == "live":
                st.page_link(tool["page"], label=f"Open {tool['title']}", icon="➡️")
            else:
                st.markdown(
                    "<span style='background:#eee;color:#888;padding:2px 10px;"
                    "border-radius:12px;font-size:0.8rem;'>Coming soon</span>",
                    unsafe_allow_html=True,
                )

st.divider()
st.caption(
    f"{len(live)} tool{'s' if len(live) != 1 else ''} available"
    + (f" · {len(soon)} on the way" if soon else "")
    + ".  Use the sidebar (top-left **»**) to switch tools at any time."
)
