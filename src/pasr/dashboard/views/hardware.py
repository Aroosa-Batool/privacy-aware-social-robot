from __future__ import annotations

import streamlit as st

from pasr.dashboard.components.save_bar import save_bar, settings_version
from pasr.dashboard.components.schema_form import render_field
from pasr.dashboard.state import settings
from pasr.settings.loader import as_dict
from pasr.settings.schema import FollowSettings, ScanSettings

SCAN_FIELDS = ("positions", "settle_seconds", "frames_per_position", "head_speed")
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
    st.caption(
        "Before a sensitive reminder, if no other voice was heard, the head looks in these "
        "directions for silent bystanders."
    )
    for name in SCAN_FIELDS:
        edited["scan"][name] = render_field(
            name, fields[name], scan[name], f"{version}.scan.{name}"
        )

with st.container(border=True):
    st.markdown("#### Follow faces")
    st.caption(
        "A face that is cut off, too small, unclear or turned away gives a poor match. With "
        "following on, the head turns and nods towards such a face until it is in full view, "
        "then compares it with the owner and the remembered bystanders. The camera stays on "
        "while the head follows."
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
