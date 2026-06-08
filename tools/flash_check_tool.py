"""
tools/flash_check_tool.py  --  "4-Way Flash Checker" page for the SignalCheck suite.

This is a Streamlit page script (run by app.py's navigation). It must NOT call
st.set_page_config — the suite entry point (app.py) does that once.
"""

import os

import streamlit as st

import flash_check as fc

STATE_KEY = "flash_folder_results"  # namespaced so tools don't clash in session state


# ----------------------------------------------------------------------------- cached analysis
@st.cache_data(show_spinner=False)
def analyze_upload(name, data, pattern):
    """Cached so re-runs (e.g. clicking around) don't re-parse the same upload."""
    return fc.analyze_bytes(name, data, pattern)


@st.cache_data(show_spinner=False)
def analyze_path(path, mtime, pattern):
    """mtime is part of the cache key so edited files get re-read."""
    return fc.analyze_file(path, pattern)


# ----------------------------------------------------------------------------- rendering
def status_of(res):
    if res["error"]:
        return "🔴 Error"
    if res["has_flash"]:
        return "⚠️ FLASH"
    if res["flash_inactive_only"]:
        return "🟡 Disabled-only"
    return "🟢 OK"


def sort_key(res):
    order = {"⚠️ FLASH": 0, "🟡 Disabled-only": 1, "🔴 Error": 2, "🟢 OK": 3}
    return (order[status_of(res)], (res["name"] or res["file"]).lower())


def render_results(results, pattern):
    if not results:
        return
    results = sorted(results, key=sort_key)

    flash = [r for r in results if r["has_flash"]]
    inactive = [r for r in results if r["flash_inactive_only"]]
    errors = [r for r in results if r["error"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Files scanned", len(results))
    c2.metric("⚠️ 4-way flash", len(flash))
    c3.metric("🟡 Disabled-only", len(inactive))
    c4.metric("🔴 Errors", len(errors))

    if flash:
        st.error(f"**{len(flash)}** signal(s) have 4-way flash on an active schedule — see ⚠️ rows below.")
    else:
        st.success("No signals have 4-way flash on an active schedule.")

    # ---- main table ----
    table = [{
        "Status": status_of(r),
        "Intersection": r["name"] or "",
        "File": r["file"],
        "Controller ID": r["id"],
        "Flash actions": r["flash_actions"],
        "Flash day plans": r["flash_plans"],
        "Notes": r["error"] if r["error"] else "",
    } for r in results]

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="small"),
            "Intersection": st.column_config.TextColumn(width="large"),
        },
    )

    # ---- download ----
    st.download_button(
        "⬇️  Download CSV summary",
        data=fc.results_to_csv(results),
        file_name="flash_summary.csv",
        mime="text/csv",
        type="primary",
    )

    # ---- per-signal flash detail ----
    if flash:
        st.subheader("When does each signal flash?")
        for r in flash:
            with st.expander(f"⚠️  {r['name'] or r['file']}  ·  plans {r['flash_plans']}"):
                detail = [{
                    "Schedule (TOD)": d["tod"],
                    "Active days": d["days"],
                    "Day Plan": d["plan"],
                    "Runs Action": d["action"],
                    "At time": d["time"],
                } for d in r["details"] if d["active"]]
                st.dataframe(detail, use_container_width=True, hide_index=True)

    if inactive:
        with st.expander(f"🟡  {len(inactive)} signal(s) have flash configured only on disabled TOD slots"):
            st.caption("These reference a flash day plan from a schedule entry that has no weekday "
                       "enabled, so it never actually runs as configured. Worth a look, but not active.")
            st.dataframe(
                [{"Intersection": r["name"] or r["file"], "File": r["file"],
                  "Flash actions": r["flash_actions"], "Flash day plans": r["flash_plans"]}
                 for r in inactive],
                use_container_width=True, hide_index=True,
            )


# ----------------------------------------------------------------------------- UI
st.title("🚦 4-Way Flash Schedule Checker")
st.caption("Scans traffic-signal controller `.xls` exports and flags any signal whose schedule "
           "commands 4-way flash.")

with st.sidebar:
    st.header("Settings")
    pattern = st.text_input(
        "Flash pattern number", value=fc.FLASH_PATTERN,
        help="The pattern that means 4-way flash (255 on this controller family).",
    ).strip() or fc.FLASH_PATTERN

    with st.expander("How the check works"):
        st.markdown(
            f"""
1. **Actions (4.5)** — finds every Action whose Pattern = **{pattern}** (4-way flash).
2. **Adv Schedule (4.3)** — reads the **Plan** column to see which Day Plans each
   schedule entry (TOD) links to. Entries with no weekday enabled are treated as inactive.
3. **Day Plan (4.4)** — checks whether a linked Day Plan runs one of the flash actions.
4. A signal is flagged **⚠️ FLASH** when an *active* schedule entry links to a Day Plan
   that runs a flash action.
"""
        )

tab_upload, tab_folder = st.tabs(["📤  Upload files", "📁  Scan a server folder"])

with tab_upload:
    st.markdown("Drag and drop one or more `.xls` controller exports (works from any computer on the network).")
    uploads = st.file_uploader(
        "Controller .xls files", type=["xls"], accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploads:
        results = []
        bar = st.progress(0.0, text="Analyzing…")
        for i, up in enumerate(uploads):
            results.append(analyze_upload(up.name, up.getvalue(), pattern))
            bar.progress((i + 1) / len(uploads), text=f"Analyzing {up.name}")
        bar.empty()
        render_results(results, pattern)

with tab_folder:
    st.markdown("Scan a folder **on the computer running this app** (the server). "
                "Useful for a shared network drive mounted on the server.")
    folder = st.text_input("Folder path", placeholder="/path/to/folder/of/xls/files")
    recursive = st.checkbox("Include sub-folders")
    if st.button("Scan folder", type="primary"):
        if not folder:
            st.warning("Enter a folder path first.")
        elif not os.path.isdir(folder):
            st.error(f"Folder not found on the server: {folder}")
        else:
            paths = fc.gather_files(folder, recursive)
            if not paths:
                st.warning("No .xls files found in that folder.")
            else:
                results = []
                bar = st.progress(0.0, text="Analyzing…")
                for i, p in enumerate(paths):
                    results.append(analyze_path(p, os.path.getmtime(p), pattern))
                    bar.progress((i + 1) / len(paths), text=f"Analyzing {os.path.basename(p)}")
                bar.empty()
                st.session_state[STATE_KEY] = results
    # Persist folder results across reruns (button clicks reset otherwise).
    if STATE_KEY in st.session_state:
        render_results(st.session_state[STATE_KEY], pattern)
