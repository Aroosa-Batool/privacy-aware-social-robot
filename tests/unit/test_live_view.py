"""The live view's feed: what it keeps for the dashboard, for how long, and what it never keeps."""

from datetime import UTC, datetime

import numpy as np
import pytest

from pasr.domain.media import AudioChunk, Frame
from pasr.live.feed import LEVELS, VOICES, FaceMark, Level, LiveFeed, Tone

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def frame(width: int = 64, height: int = 48) -> Frame:
    return Frame(image=np.zeros((height, width, 3), np.uint8), captured_at=T0)


def chunk(rms: float) -> AudioChunk:
    return AudioChunk(samples=np.full(512, rms, np.float32), sample_rate=16000, start=T0)


def feed(enabled: bool = True) -> LiveFeed:
    return LiveFeed(lambda: enabled)


def test_nothing_is_kept_while_the_live_view_is_off():
    live = feed(enabled=False)
    with live.activity("Scanning"):
        live.face(frame(), [FaceMark(None, "Owner 0.90", Tone.OWNER)])
        live.voice(2.0, "Owner 0.90", Tone.OWNER)
    assert live.snapshot() is None


def test_only_what_happens_inside_a_step_is_kept():
    live = feed()
    live.face(frame(), [FaceMark(None, "before", Tone.OWNER)])
    assert live.snapshot().image is None

    with live.activity("Reminder #1: scanning the room", "threshold 0.40"):
        marks = [FaceMark((1, 2, 3, 4), "Owner 0.80", Tone.OWNER)]
        live.face(frame(), marks, note="looking left")
        view = live.snapshot()
        assert view.active
        assert (view.title, view.detail) == ("Reminder #1: scanning the room", "threshold 0.40")
        assert view.faces == tuple(marks) and view.note == "looking left"
        assert view.image.shape == (48, 64, 3)
    live.face(frame(), [FaceMark(None, "after", Tone.OTHER)])

    view = live.snapshot()  # the frame went with its step: no last frame stays on show
    assert not view.active
    assert (view.image, view.faces, view.note) == (None, (), "")


def test_the_microphone_panel_keeps_levels_and_the_latest_voices():
    live = feed()
    with live.activity("Listening"):
        live.audio(chunk(0.1), speech=0.9, threshold=0.5)
        live.audio(chunk(0.001), speech=0.1, threshold=0.5)
        for n in range(VOICES + 2):
            live.voice(2.04, f"segment {n}", Tone.OWNER)
        view = live.snapshot()
    assert view.levels == (Level(-20.0, True), Level(-60.0, False))
    assert (view.speech, view.speech_threshold) == (0.1, 0.5)
    assert [voice.label for voice in view.voices] == [
        f"segment {n}" for n in range(VOICES + 1, 1, -1)
    ]
    assert view.voices[0].seconds == 2.0 and view.microphone_live


def test_the_level_history_is_bounded():
    live = feed()
    with live.activity("Listening"):
        for _ in range(LEVELS + 10):
            live.audio(chunk(0.1), speech=0.9, threshold=0.5)
    assert len(live.snapshot().levels) == LEVELS


def test_a_new_step_starts_the_microphone_panel_afresh_and_shows_no_earlier_frame():
    live = feed()
    with live.activity("Scanning"):
        live.face(frame(), [FaceMark((1, 2, 3, 4), "Someone else", Tone.OTHER)])
    with live.activity("Listening"):
        live.voice(2.0, "first", Tone.OWNER)
    with live.activity("Listening again"):
        live.voice(2.0, "second", Tone.OTHER)
        view = live.snapshot()
    assert [voice.label for voice in view.voices] == ["second"]
    assert (view.image, view.faces) == (None, ())  # nobody from the scan is shown any more


def test_wide_frames_are_shrunk_with_their_boxes():
    live = feed()
    with live.activity("Scanning"):
        live.face(frame(1920, 1080), [FaceMark((100, 200, 300, 400), "Owner", Tone.OWNER)])
        view = live.snapshot()
    assert view.image.shape == (540, 960, 3)
    assert view.faces[0].box == (50, 100, 150, 200)


def test_switching_the_live_view_off_drops_what_it_holds():
    enabled = True
    live = LiveFeed(lambda: enabled)
    with live.activity("Scanning"):
        live.face(frame(), [])
    enabled = False
    assert live.snapshot() is None
    enabled = True
    assert live.snapshot().image is None and live.snapshot().step == 0


def test_clearing_forgets_everything():
    live = feed()
    with live.activity("Scanning"):
        live.face(frame(), [])
        live.voice(2.0, "Owner", Tone.OWNER)
    live.clear()
    view = live.snapshot()
    assert (view.image, view.voices, view.step) == (None, (), 0)


@pytest.mark.parametrize("rms", [0.0, 1e-9])
def test_silence_reads_as_the_floor(rms: float):
    live = feed()
    with live.activity("Listening"):
        live.audio(chunk(rms), speech=0.0, threshold=0.5)
    assert live.snapshot().levels[-1].db == -120.0
