"""
live_time_slider.py  --  A time-of-day slider that streams its value to Streamlit
*while you drag it* (the built-in st.slider only updates on release).

Returns the selected minute-of-day (int, 0..1439). Self-contained static
component (no internet/build step needed).
"""

import os

import streamlit.components.v1 as components

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_slider_component")
_component = components.declare_component("live_time_slider", path=_DIR)


def live_time_slider(value=720, min_value=0, max_value=1439, step=5, ticks=None, key=None):
    """Render the slider. `value` is the initial minute-of-day; returns the
    current minute-of-day. `ticks` is a list of minutes-of-day to draw as vertical
    tick marks on the track. To force a new initial value (e.g. a 'Now' button),
    change `key` so the component remounts."""
    result = _component(value=int(value), min=int(min_value), max=int(max_value),
                        step=int(step), ticks=[int(t) for t in (ticks or [])],
                        key=key, default=int(value))
    try:
        return int(result)
    except (TypeError, ValueError):
        return int(value)
