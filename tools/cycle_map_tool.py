"""
tools/cycle_map_tool.py  --  "Cycle Length Map" page for the SignalCheck suite.

Upload many controller .xls timing sheets + a CSV of signal locations, pick a
date and time, and see each intersection on a map colored by the cycle length it
is running at that moment. Move the date/time and the map updates.

A Streamlit page script — does not call st.set_page_config (app.py does).
"""

import colorsys
import datetime as dt

import streamlit as st

import cycle_schedule as cs
import live_time_slider as lts
from st_compat import STRETCH

STATE_DATE = "cyc_date"

# Colors for the non-coordinated states
COLOR_FLASH = [214, 40, 40]
COLOR_FREE = [150, 150, 150]
COLOR_NONE = [90, 90, 90]
COLOR_OFF = [200, 200, 200]   # signals not in any corridor (Corridors view)

# Distinct colors for corridors (tab10-style)
CORRIDOR_PALETTE = [
    [31, 119, 180], [255, 127, 14], [44, 160, 44], [214, 39, 40], [148, 103, 189],
    [140, 86, 75], [227, 119, 194], [127, 127, 127], [188, 189, 34], [23, 190, 207],
]


# ----------------------------------------------------------------------------- cached parsing
@st.cache_data(show_spinner=False)
def load_model(name, data):
    return cs.build_model_bytes(name, data)


@st.cache_data(show_spinner=False)
def load_locations(data):
    return cs.parse_locations_csv(data)


# ----------------------------------------------------------------------------- helpers
def coord_color(cycle, cmin, cmax):
    """Green (short cycle) -> orange (long cycle)."""
    span = (cmax - cmin) or 1
    frac = max(0.0, min(1.0, (cycle - cmin) / span))
    hue = (120 - 90 * frac) / 360.0  # 120°=green -> 30°=orange
    r, g, b = colorsys.hsv_to_rgb(hue, 0.78, 0.92)
    return [int(r * 255), int(g * 255), int(b * 255)]


def color_for(res, cmin, cmax):
    state = res["state"]
    if state == "flash":
        return COLOR_FLASH
    if state == "free":
        return COLOR_FREE
    if state == "coord" and res["cycle"]:
        return coord_color(res["cycle"], cmin, cmax)
    return COLOR_NONE


# Color ramp for implied progression speed (mph): red(slow) -> green(~30) -> blue(fast)
SPEED_STOPS = [
    (15, [200, 40, 40]), (22, [235, 140, 40]), (28, [240, 205, 40]),
    (32, [46, 180, 80]), (40, [40, 170, 160]), (50, [40, 110, 200]),
]


def speed_color(mph):
    if mph is None:
        return COLOR_OFF
    if mph <= SPEED_STOPS[0][0]:
        return SPEED_STOPS[0][1]
    if mph >= SPEED_STOPS[-1][0]:
        return SPEED_STOPS[-1][1]
    for (v0, c0), (v1, c1) in zip(SPEED_STOPS, SPEED_STOPS[1:]):
        if v0 <= mph <= v1:
            t = (mph - v0) / (v1 - v0)
            return [int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3)]
    return COLOR_OFF


def fmt_date(d):
    """'Wednesday, June 10, 2026' — cross-platform.

    Builds the string with zero-padded directives (valid on Windows, Linux, and
    macOS), then strips the day's leading zero. Avoids the Unix-only %-d / %-I
    and the Windows-only %#d / %#I directives, which raise 'Invalid format
    string' on the other platform."""
    return d.strftime("%A, %B %d, %Y").replace(" 0", " ")


def fmt_time(t):
    """'3:07 PM' — cross-platform (strips the hour's leading zero)."""
    return t.strftime("%I:%M %p").lstrip("0")


def minute_to_label(m):
    """Minute-of-day (0..1440) -> '3:07 PM'. 1440 (end of day) shows as 12:00 AM."""
    m = 0 if int(m) >= 1440 else int(m)
    return fmt_time(dt.time(m // 60, m % 60))


# ----------------------------------------------------------------------------- UI
st.title("🗺️ Cycle Length Map")
st.caption("See what cycle length every signal is running at a chosen date & time. "
           "Resolves Adv Schedule → Day Plan → Actions → Patterns for each controller.")

with st.sidebar:
    st.header("Data")
    sheets = st.file_uploader(
        "Timing sheets (.xls) — one per controller",
        type=["xls"], accept_multiple_files=True,
    )
    st.markdown("**Signal locations CSV**")
    loc_file = st.file_uploader(
        "Columns: id, latitude, longitude (name optional)",
        type=["csv"], label_visibility="collapsed",
    )
    st.download_button("⬇️ CSV template", cs.LOCATIONS_TEMPLATE,
                       "locations_template.csv", "text/csv")
    st.caption("The **ID** in each CSV row is matched to the number in the timing-sheet "
               "file name (e.g. `…_31.xls` → ID 31).")

    st.divider()
    st.header("Corridor grouping")
    corridor_miles = st.slider(
        "Max spacing between adjacent signals (miles)",
        min_value=0.1, max_value=2.0, value=0.5, step=0.05,
        help="Two signals are 'adjacent' if they're within this distance "
             "(~0.5 mi ≈ 2,640 ft is typical signal spacing).",
    )
    corridor_half = st.checkbox(
        "Group half-cycle (double-cycling) signals", value=True,
        help="Treat a signal running half the corridor's cycle (e.g. 60 within a "
             "120 corridor) as part of the same corridor.",
    )

if not sheets:
    st.info("⬅️ Upload one or more controller `.xls` timing sheets in the sidebar to begin. "
            "Add a locations CSV to place them on the map.")
    st.stop()

# ---- Parse everything (cached) ----
models = [load_model(f.name, f.getvalue()) for f in sheets]
locations, loc_error = ({}, None)
if loc_file is not None:
    locations, loc_error = load_locations(loc_file.getvalue())
    if loc_error:
        st.warning(f"Locations CSV: {loc_error}")

# ---- Metrics row lives at the TOP; it's filled in after we resolve below ----
metrics_box = st.container()
st.divider()

# ---- Date & time controls (kept right above the map) ----
now = dt.datetime.now()
if STATE_DATE not in st.session_state:
    st.session_state[STATE_DATE] = now.date()
if "cyc_default_min" not in st.session_state:
    st.session_state["cyc_default_min"] = (now.hour * 60 + now.minute) // 5 * 5


def reset_to_now():
    n = dt.datetime.now()
    st.session_state[STATE_DATE] = n.date()
    st.session_state["cyc_default_min"] = (n.hour * 60 + n.minute) // 5 * 5
    # changing the slider key remounts it so it re-initialises to "now"
    st.session_state["cyc_nonce"] = st.session_state.get("cyc_nonce", 0) + 1


c_date, c_btn = st.columns([3, 1])
with c_date:
    sel_date = st.date_input("📅 Date", key=STATE_DATE)
with c_btn:
    st.write("")
    st.write("")
    st.button("⏱ Now", on_click=reset_to_now,
              help="Jump to the current date & time", **STRETCH)

# Tick marks on the slider: union of cycle/state transition times for the selected
# date, but ONLY for the signals currently visible in the map's viewport. The map
# reports its bounds (read here from the previous run); a signal outside the view
# contributes no ticks.
def _in_view(loc, bounds):
    if not bounds:
        return True  # before the map reports, include all mapped signals
    return (bounds["south"] <= loc["lat"] <= bounds["north"]
            and bounds["west"] <= loc["lon"] <= bounds["east"])


map_bounds = st.session_state.get("cyc_map")  # bounds reported by the map last run
if locations:
    mapped_models = [m for m in models
                     if m.get("file_id") and cs.norm_id(m["file_id"]) in locations]
    tick_models = [m for m in mapped_models
                   if _in_view(locations[cs.norm_id(m["file_id"])], map_bounds)]
else:
    mapped_models, tick_models = [], models

tick_set = set()
for tm in tick_models:
    tick_set.update(cs.transition_minutes(tm, sel_date))
ticks = sorted(tick_set)

nonce = st.session_state.get("cyc_nonce", 0)
minutes = lts.live_time_slider(
    value=st.session_state["cyc_default_min"], step=5, ticks=ticks,
    key=f"cyc_time_{nonce}")
sel_time = dt.time(minutes // 60, minutes % 60)
when = dt.datetime.combine(sel_date, sel_time)
date_str = fmt_date(when)
time_str = fmt_time(when)
st.markdown(f"#### Showing **{date_str}** at **{time_str}**")
if ticks or (locations and map_bounds):
    in_view = f"{len(tick_models)} of {len(mapped_models)} signals in view" \
        if (locations and map_bounds) else "all mapped signals"
    st.caption(f"⏱ Tick marks: {len(ticks)} cycle-length change(s) on this day "
               f"({in_view}). Zoom/pan the map to change which signals are counted.")

# ---- Resolve every controller at this datetime ----
resolved = []
for m in models:
    res = cs.resolve(m, when)
    loc = locations.get(cs.norm_id(m["file_id"])) if m["file_id"] else None
    resolved.append({"model": m, "res": res, "loc": loc})

coord_cycles = [r["res"]["cycle"] for r in resolved
                if r["res"]["state"] == "coord" and r["res"]["cycle"]]
cmin = min(coord_cycles) if coord_cycles else 0
cmax = max(coord_cycles) if coord_cycles else 0

# ---- Fill the metrics row at the top of the page ----
with metrics_box:
    n_coord = sum(1 for r in resolved if r["res"]["state"] == "coord")
    n_free = sum(1 for r in resolved if r["res"]["state"] == "free")
    n_flash = sum(1 for r in resolved if r["res"]["state"] == "flash")
    n_err = sum(1 for r in resolved if r["res"]["state"] in ("error", "none"))
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Controllers", len(resolved))
    mc2.metric("🟢 Coordinated", n_coord)
    mc3.metric("⚪ Free", n_free)
    mc4.metric("🔴 Flash", n_flash)
    mc5.metric("⚠️ Unreadable", n_err)

# ---- Map ----
mapped = [r for r in resolved if r["loc"]]
unmapped = [r for r in resolved if not r["loc"]]

# Compute corridors first (needed for the corridor map lines AND the table below).
when_min = when.hour * 60 + when.minute
corr_signals = []
for r in mapped:
    res, loc, m = r["res"], r["loc"], r["model"]
    if res["state"] != "coord" or not res["cycle"]:
        continue                           # only coordinated signals form corridors
    if not _in_view(loc, map_bounds):
        continue                           # only signals in the current map view
    seg_start, seg_end = cs.segment_bounds(cs.transition_minutes(m, sel_date), when_min)
    corr_signals.append({
        "id": str(m["file_id"]),
        "name": loc["name"] or m["name"] or m["file"],
        "lat": loc["lat"], "lon": loc["lon"], "cycle": res["cycle"],
        "offset": res["offset"], "seg_start": seg_start, "seg_end": seg_end,
    })
corridors = cs.build_corridors(corr_signals, corridor_miles, corridor_half, min_size=2)
# Assign a color to each corridor and map each member signal id -> corridor color.
corridor_color_of = {}
for i, c in enumerate(corridors):
    c["color"] = CORRIDOR_PALETTE[i % len(CORRIDOR_PALETTE)]
    for mem in c["members"]:
        corridor_color_of[str(mem["id"])] = c["color"]

if not locations:
    st.info("Upload a **locations CSV** in the sidebar to plot the signals on a map. "
            "The results table below works without it.")
elif not mapped:
    st.warning("None of the uploaded timing sheets matched an ID in the locations CSV. "
               "Check that the file-name numbers match the CSV `id` column.")
else:
    import live_map as lm

    col_view, col_color = st.columns([1, 1.4])
    with col_view:
        map_view = st.radio("Map view", ["Signals", "Corridors"], horizontal=True,
                            key="cyc_view", help="Signals: dots colored by cycle. "
                            "Corridors: signals linked into corridor lines.")
    corridor_mode = (map_view == "Corridors")
    color_by = "Corridor"
    with col_color:
        if corridor_mode:
            color_by = st.radio("Color corridor lines by", ["Corridor", "Progression speed"],
                                horizontal=True, key="cyc_color",
                                help="Progression speed colors each link by implied mph "
                                "(link distance ÷ offset difference).")
    speed_mode = corridor_mode and color_by == "Progression speed"

    points = []
    for r in mapped:
        res, loc, m = r["res"], r["loc"], r["model"]
        sid = str(m["file_id"])
        name = loc["name"] or m["name"] or m["file"]
        tip = (f"<b>{name}</b> (ID {m['file_id']})<br/>"
               f"Status: {res['label']}<br/>"
               f"Plan {res['plan']} · Action {res['action']} · Pattern {res['pattern']}")
        if speed_mode:
            color = [80, 80, 80] if sid in corridor_color_of else COLOR_OFF
        elif corridor_mode:
            color = corridor_color_of.get(sid, COLOR_OFF)   # gray if not in a corridor
        else:
            color = color_for(res, cmin, cmax)
        points.append({"id": sid, "lat": loc["lat"], "lon": loc["lon"],
                       "color": color, "tip": tip})

    lines = []
    if speed_mode:
        # one short line per link, colored by that link's implied progression speed
        for c in corridors:
            oms = c["ordered_members"]
            for (a, b), ln in zip(zip(oms, oms[1:]), cs.corridor_links(c)):
                lines.append({"coords": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]],
                              "color": speed_color(ln["speed_mph"])})
    elif corridor_mode:
        lines = [{"coords": c["path"], "color": c["color"]} for c in corridors]

    center = [sum(p["lat"] for p in points) / len(points),
              sum(p["lon"] for p in points) / len(points)]
    # The map reports its viewport bounds via st.session_state["cyc_map"]; we read
    # those at the top of the next run to filter ticks and corridors to the view.
    lm.live_map(points, center=center, zoom=12, height=520, lines=lines, key="cyc_map")

    # ---- Legend ----
    def chip(rgb, text):
        return (f"<span style='display:inline-flex;align-items:center;margin-right:14px;'>"
                f"<span style='width:14px;height:14px;border-radius:50%;background:rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                f"border:1px solid #fff;box-shadow:0 0 0 1px #aaa;margin-right:6px;'></span>{text}</span>")

    if speed_mode:
        if corridors:
            grad = "linear-gradient(to right, rgb(200,40,40), rgb(235,140,40), "\
                   "rgb(240,205,40), rgb(46,180,80), rgb(40,170,160), rgb(40,110,200))"
            legend = (
                "<span style='display:inline-flex;align-items:center;'>"
                "Implied progression&nbsp; <b>15</b>&nbsp;"
                f"<span style='display:inline-block;width:180px;height:12px;border-radius:6px;"
                f"background:{grad};border:1px solid #aaa;margin:0 6px;'></span>"
                "<b>50+ mph</b></span>"
            )
        else:
            legend = "No corridors in view at this time."
    elif corridor_mode:
        if corridors:
            legend = "".join(chip(c["color"], f"{c['label']} ({c['cycle_main']}s)")
                             for c in corridors)
            legend += chip(COLOR_OFF, "not in a corridor")
        else:
            legend = "No corridors in view at this time."
    else:
        legend = chip(COLOR_FREE, "Free") + chip(COLOR_FLASH, "Flash")
        if coord_cycles:
            grad = "linear-gradient(to right, rgb(46,180,80), rgb(245,200,30), rgb(235,140,40))"
            legend += (
                "<span style='display:inline-flex;align-items:center;'>"
                f"Cycle&nbsp; <b>{cmin}s</b>&nbsp;"
                f"<span style='display:inline-block;width:140px;height:12px;border-radius:6px;"
                f"background:{grad};border:1px solid #aaa;margin:0 6px;'></span>"
                f"<b>{cmax}s</b></span>"
            )
    st.markdown("<div style='margin-top:6px'>" + legend + "</div>", unsafe_allow_html=True)

# ---- Corridors table (just below the map) ----
if locations and mapped:
    st.subheader("Corridors in view")
    if not corridors:
        st.info("No corridors right now — no adjacent in-view signals share a "
                "(half-)cycle length at this time. Try a larger spacing in the sidebar, "
                "pan/zoom to a coordinated area, or pick a coordinated time of day.")
    else:
        crows = []
        for c in corridors:
            cyc = (" / ".join(f"{x}s" for x in c["cycles"])
                   if len(c["cycles"]) > 1 else f"{c['cycle_main']}s")
            crows.append({
                "Corridor": c["label"],
                "Signals": c["size"],
                "Cycle": cyc,
                "Starts": minute_to_label(c["start"]),
                "Ends": minute_to_label(c["end"]),
                "Member signals": ", ".join(m["name"] for m in c["members"]),
            })
        st.dataframe(crows, hide_index=True, **STRETCH)
        st.caption(
            f"{len(corridors)} corridor(s) at {time_str}, within the current map view. "
            "A corridor = adjacent signals (within the sidebar spacing) sharing the same "
            "cycle (or half/double cycle). Start/Stop is the window during which every "
            "member holds these cycles. Zoom/pan the map to change which signals count.")

# ---- Results table ----
st.subheader("All controllers at this time")
badge = {"coord": "🟢", "free": "⚪", "flash": "🔴", "none": "⚠️", "error": "⚠️"}
table = []
for r in resolved:
    m, res = r["model"], r["res"]
    table.append({
        "": badge.get(res["state"], ""),
        "ID": m["file_id"] or "",
        "Intersection": (r["loc"]["name"] if r["loc"] and r["loc"]["name"] else m["name"]) or m["file"],
        "Cycle / State": res["label"],
        "Day Plan": res["plan"],
        "TOD": res["tod"],
        "Action": res["action"],
        "Pattern": res["pattern"],
        "On map": "✓" if r["loc"] else "—",
        "Notes": m["error"] or "",
    })
st.dataframe(table, hide_index=True, **STRETCH)

if unmapped and locations:
    st.caption("Not on map (no matching location ID): "
               + ", ".join(sorted(str(r["model"]["file_id"]) for r in unmapped)))

# ---- Progression speed table (bottom of page) ----
if locations and mapped and corridors:
    st.subheader("Implied progression speeds (mph)")
    link_lists = [cs.corridor_links(c) for c in corridors]
    maxk = max((len(ll) for ll in link_lists), default=0)
    prows = []
    for c, ll in zip(corridors, link_lists):
        speeds = [ln["speed_mph"] for ln in ll]
        valid = [s for s in speeds if s is not None]
        row = {"Corridor": c["label"], "Signals": c["size"],
               "Avg mph": f"{sum(valid) / len(valid):.0f}" if valid else "—"}
        for k in range(maxk):
            if k >= len(speeds):
                row[f"Link {k + 1}"] = ""
            else:
                row[f"Link {k + 1}"] = f"{speeds[k]:.0f}" if speeds[k] is not None else "—"
        prows.append(row)
    st.dataframe(prows, hide_index=True, **STRETCH)
    st.caption(
        "Implied progression speed for each link = straight-line distance between the two "
        "signals ÷ their offset difference (Patterns 2.4 'Offset'), converted to mph. Links "
        "are numbered in order along each corridor's drawn line. '—' = offsets equal (no "
        "implied movement) or not computable.")

with st.expander("How a controller's state is determined / assumptions"):
    st.markdown(
        """
- **Schedule precedence:** when several Adv Schedule (4.3) entries match the date,
  the **most specific** one wins (fewest enabled day/month/date bits) — this lets a
  holiday entry override the weekly default and the all-on catch-all.
- **Time of day:** within the chosen Day Plan (4.4), the event whose time is the
  latest at or before the selected time sets the Action.
- **Action → Pattern → Cycle:** via Actions (4.5) and Patterns (2.4).
- **Specials:** Pattern **255 = Flash**, Pattern **254 = Free**, and any pattern with
  a **0** cycle length is shown as **Free**.
- **Implied progression speed:** for each corridor link, the signals' **offset**
  difference (Patterns 2.4, seconds, taken as the smaller value modulo the cycle) is
  used as the travel time, divided into the straight-line link distance → mph. This
  is an *implied* speed from the offsets, not a measured one, and uses straight-line
  (not along-street) distance.
- The map basemap needs internet access; dots still render offline.
"""
    )
