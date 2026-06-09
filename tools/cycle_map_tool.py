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

STATE_DATE = "cyc_date"
STATE_TIME = "cyc_time"

# Colors for the non-coordinated states
COLOR_FLASH = [214, 40, 40]
COLOR_FREE = [150, 150, 150]
COLOR_NONE = [90, 90, 90]


# ----------------------------------------------------------------------------- cached parsing
@st.cache_data(show_spinner=False)
def load_model(name, data):
    return cs.build_model_bytes(name, data)


@st.cache_data(show_spinner=False)
def load_locations(data):
    return cs.parse_locations_csv(data)


# ----------------------------------------------------------------------------- helpers
def round_to_step(t, minutes=15):
    total = (t.hour * 60 + t.minute) // minutes * minutes
    return dt.time(total // 60, total % 60)


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

# ---- Date & time controls ----
now = dt.datetime.now()
if STATE_DATE not in st.session_state:
    st.session_state[STATE_DATE] = now.date()
if STATE_TIME not in st.session_state:
    st.session_state[STATE_TIME] = round_to_step(now.time())


def reset_to_now():
    n = dt.datetime.now()
    st.session_state[STATE_DATE] = n.date()
    st.session_state[STATE_TIME] = round_to_step(n.time())


c_date, c_time, c_btn = st.columns([1.1, 2.2, 0.8])
with c_date:
    sel_date = st.date_input("📅 Date", key=STATE_DATE)
with c_time:
    sel_time = st.slider(
        "🕑 Time of day", key=STATE_TIME,
        min_value=dt.time(0, 0), max_value=dt.time(23, 45),
        step=dt.timedelta(minutes=15), format="h:mm a",
    )
with c_btn:
    st.write("")
    st.write("")
    st.button("⏱ Now", on_click=reset_to_now, use_container_width=True)

when = dt.datetime.combine(sel_date, sel_time)
st.markdown(f"#### Showing **{when:%A, %B %-d, %Y}** at **{when:%-I:%M %p}**")

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

# ---- Summary metrics ----
n_coord = sum(1 for r in resolved if r["res"]["state"] == "coord")
n_free = sum(1 for r in resolved if r["res"]["state"] == "free")
n_flash = sum(1 for r in resolved if r["res"]["state"] == "flash")
n_err = sum(1 for r in resolved if r["res"]["state"] in ("error", "none"))
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Controllers", len(resolved))
m2.metric("🟢 Coordinated", n_coord)
m3.metric("⚪ Free", n_free)
m4.metric("🔴 Flash", n_flash)
m5.metric("⚠️ Unreadable", n_err)

# ---- Map ----
mapped = [r for r in resolved if r["loc"]]
unmapped = [r for r in resolved if not r["loc"]]

if not locations:
    st.info("Upload a **locations CSV** in the sidebar to plot the signals on a map. "
            "The results table below works without it.")
elif not mapped:
    st.warning("None of the uploaded timing sheets matched an ID in the locations CSV. "
               "Check that the file-name numbers match the CSV `id` column.")
else:
    import pydeck as pdk

    points = []
    for r in mapped:
        res, loc, m = r["res"], r["loc"], r["model"]
        label = res["label"]
        name = loc["name"] or m["name"] or m["file"]
        tip = (f"<b>{name}</b> (ID {m['file_id']})<br/>"
               f"Status: {label}<br/>"
               f"Plan {res['plan']} · Action {res['action']} · Pattern {res['pattern']}")
        points.append({
            "lon": loc["lon"], "lat": loc["lat"],
            "color": color_for(res, cmin, cmax) + [220],
            "name": name, "tip": tip,
        })

    center_lat = sum(p["lat"] for p in points) / len(points)
    center_lon = sum(p["lon"] for p in points) / len(points)

    layer = pdk.Layer(
        "ScatterplotLayer", data=points,
        get_position="[lon, lat]", get_fill_color="color",
        get_radius=90, radius_min_pixels=8, radius_max_pixels=34,
        pickable=True, stroked=True, get_line_color=[255, 255, 255],
        line_width_min_pixels=1.5,
    )
    view = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=12)
    deck = pdk.Deck(
        layers=[layer], initial_view_state=view,
        map_provider="carto", map_style="light",
        tooltip={"html": "{tip}", "style": {"backgroundColor": "#222", "color": "white"}},
    )
    st.pydeck_chart(deck, use_container_width=True)

    # ---- Legend ----
    def chip(rgb, text):
        return (f"<span style='display:inline-flex;align-items:center;margin-right:14px;'>"
                f"<span style='width:14px;height:14px;border-radius:50%;background:rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                f"border:1px solid #fff;box-shadow:0 0 0 1px #aaa;margin-right:6px;'></span>{text}</span>")

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
st.dataframe(table, use_container_width=True, hide_index=True)

if unmapped and locations:
    st.caption("Not on map (no matching location ID): "
               + ", ".join(sorted(str(r["model"]["file_id"]) for r in unmapped)))

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
- The map basemap needs internet access; dots still render offline.
"""
    )
