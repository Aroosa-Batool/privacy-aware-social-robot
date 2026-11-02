"""What the robot is being tested with: a real person, or pictures shown to the camera and
recordings played through speakers. Switched on Home or with a quick test; each reminder run logs
it as it starts (``flow.started``), so runs and the feedback on them can be compared by it
(ADR 0014). A label only: the camera and microphone work the same either way."""

from __future__ import annotations

import streamlit as st

from pasr.dashboard.state import save_settings, settings

REAL, MEDIA = "real_person", "pictures_and_recordings"
WORDS = {REAL: "a real person", MEDIA: "pictures and recordings"}
LABEL = "Testing with pictures & recordings"
HELP = (
    "On: you show the robot pictures and play recordings (a video, for example) through "
    "speakers. Off: real people are in the room. Each reminder run logs which as it starts, so "
    "you can compare them; switch before adding a test. The camera and microphone work the same "
    "either way."
)


def media() -> bool:
    return settings().study.tested_with == MEDIA


def save(with_media: bool) -> None:
    """Applies at once, also to a running robot: from its next reminder run."""
    if with_media != media():
        save_settings({"study": {"tested_with": MEDIA if with_media else REAL}})


def switch() -> bool:
    """The toggle, saved as soon as it is switched; returns what it is set to."""
    on = st.toggle(LABEL, value=media(), help=HELP)
    save(on)
    return on
