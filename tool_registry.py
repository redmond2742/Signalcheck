"""
tool_registry.py  --  Central catalog for the SignalCheck tool suite.

This is the ONE place you edit to add a new tool. The home page and the
navigation sidebar are both built automatically from this list.

To add a tool:
  1. Copy  tools/_template_tool.py  to  tools/your_tool.py  and build its UI.
  2. Add an entry to TOOLS below.
That's it — it appears on the home page and in the sidebar.
"""

# --- Suite branding (change these to rebrand the whole app) -------------------
SUITE_NAME = "SignalCheck"
SUITE_ICON = "🚦"
SUITE_TAGLINE = "Traffic Signal Timing Sheet Toolkit"
SUITE_BLURB = (
    "A growing toolkit for inspecting and auditing traffic-signal controller "
    "timing-sheet exports — fast checks across many intersections at once."
)

# --- The tools ----------------------------------------------------------------
# Each entry:
#   key       unique short id (used for routing / state namespacing)
#   title     display name
#   icon      emoji shown on the card and in the sidebar
#   page      path to the page script (relative to this folder)
#   tagline   one-line description for the home-page card
#   status    "live" (clickable) or "soon" (shown as Coming soon)
TOOLS = [
    {
        "key": "flash",
        "title": "4-Way Flash Checker",
        "icon": "🚦",
        "page": "tools/flash_check_tool.py",
        "tagline": "Scan controller .xls exports and flag any signal whose schedule "
                   "commands 4-way flash (pattern 255).",
        "status": "live",
    },
    {
        "key": "cyclemap",
        "title": "Cycle Length Map",
        "icon": "🗺️",
        "page": "tools/cycle_map_tool.py",
        "tagline": "Map every signal's cycle length at any date & time. Upload many "
                   "timing sheets + a locations CSV; scrub the calendar/time slider.",
        "status": "live",
    },

    # ---- Add new tools below. Example of a placeholder/coming-soon entry: -----
    # {
    #     "key": "splitmon",
    #     "title": "Split Monitor Auditor",
    #     "icon": "📊",
    #     "page": "tools/split_monitor_tool.py",
    #     "tagline": "Compare programmed splits against split-monitor settings.",
    #     "status": "soon",
    # },
]


def live_tools():
    return [t for t in TOOLS if t.get("status", "live") == "live"]
