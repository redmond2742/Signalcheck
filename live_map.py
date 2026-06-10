"""
live_map.py  --  An interactive Leaflet map component that reports its current
viewport bounds back to Streamlit on every pan/zoom.

Returns the latest bounds as {"north","south","east","west","zoom"} (or None
before the map has reported). Use the bounds to react to what's visible — e.g.
only count signals currently in view.

Leaflet is vendored under map_component/vendor, so the library works offline
(only the basemap tiles need internet, the same as before).
"""

import os

import streamlit.components.v1 as components

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_component")
_component = components.declare_component("live_map", path=_DIR)


def live_map(points, center, zoom=12, height=520, key=None):
    """Render the map.

    points : list of {"id", "lat", "lon", "color":[r,g,b], "tip": html}
    center : [lat, lon] used only on first render (view persists afterwards)
    Returns the current viewport bounds dict, or None until first reported.
    """
    return _component(points=points, center=list(center), zoom=int(zoom),
                      height=int(height), default=None, key=key)
