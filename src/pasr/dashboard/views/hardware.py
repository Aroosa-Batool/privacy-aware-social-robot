from __future__ import annotations

import streamlit as st

from pasr.dashboard.components.save_bar import save_bar, settings_version
from pasr.dashboard.components.schema_form import render_field
from pasr.dashboard.state import settings
from pasr.settings.loader import as_dict
from pasr.settings.schema import FollowSettings, ScanSettings

SCAN_FIELDS = (
    "positions",
    "tilts",
    "study_seconds",
    "settle_seconds",
    "frames_per_position",
    "head_speed",
)
# Following is switched on or off here; how far the head moves keeps its values (``pasr config``).

st.title("Hardware")
st.caption(
    "How the robot's head moves: where it looks for silent bystanders, and whether it follows a "
    "face it does not see in full."
)

version = settings_version()
values = as_dict(settings())
scan, fields = values["scan"], ScanSettings.model_fields
follow, follow_fields = dict(scan["follow"]), FollowSettings.model_fields
edited = {"scan": dict(scan)}

with st.container(border=True):
    st.markdown("#### Room scan")
    reminder = values["reminder"]
    scan_minutes = reminder["wake_lead_minutes"] - reminder["listen_window_minutes"]
    st.caption(
        "Before a sensitive reminder, if no other voice was heard, the head sweeps the room for "
        f"silent bystanders until the due time (the last {scan_minutes:g} minutes): each row, "
        "every direction. A face it does not recognise at once, it looks at closer before "
        "moving on. Someone you allowed before is noted and the sweep goes on; once it finds "
        "someone it must ask you about, or someone you declined for, it stops."
    )
    for name in SCAN_FIELDS:
        edited["scan"][name] = render_field(
            name, fields[name], scan[name], f"{version}.scan.{name}"
        )

with st.container(border=True):
    st.markdown("#### Follow faces")
    st.caption(
        "A face that is cut off, too small, unclear or turned away gives a poor match. With "
        "following on, while the robot looks closer at a face it did not recognise at once, the "
        "head also turns and nods towards it until it is in full view."
    )
    follow["enabled"] = render_field(
        "enabled",
        follow_fields["enabled"],
        follow["enabled"],
        f"{version}.scan.follow.enabled",
        label="Follow faces that are not in full view",
    )
edited["scan"]["follow"] = follow

save_bar(edited, values)
