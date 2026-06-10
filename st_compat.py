"""
st_compat.py  --  Small shims for Streamlit API changes across versions.

`use_container_width=True` was deprecated (Streamlit 1.49) in favor of
`width="stretch"`. Spread STRETCH into width-able calls so the code uses the new
API on new Streamlit (no deprecation warning) and still works on older versions:

    st.dataframe(df, hide_index=True, **STRETCH)
"""

import streamlit as st


def _version_tuple(v):
    out = []
    for part in v.split(".")[:3]:
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


# width="stretch"/"content" + use_container_width deprecation landed in 1.49.
if _version_tuple(st.__version__) >= (1, 49, 0):
    STRETCH = {"width": "stretch"}
else:
    STRETCH = {"use_container_width": True}
