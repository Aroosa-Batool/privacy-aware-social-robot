"""The live view's frame drawing and its desktop window: the pipe format, when the window opens
and closes, the window process, and how the window draws (rendered without a screen)."""

import asyncio
import io
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np

from pasr.domain.media import Frame
from pasr.live import desktop, wire
from pasr.live.desktop import DesktopWindow, WindowProcess
from pasr.live.feed import FaceMark, Level, LiveFeed, LiveView, Tone, VoiceMark
from pasr.live.window import CAMERA, HEIGHT, MICROPHONE, WIDTH, annotate, ascii_text, bgr, render
from support.live import Windows

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def frame(value: int = 0) -> Frame:
    return Frame(image=np.full((100, 100, 3), value, np.uint8), captured_at=T0)


def scanning(*faces: FaceMark) -> LiveView:
    return LiveView(
        title="Scanning", active=True, step=2, image=np.zeros((100, 100, 3), np.uint8), faces=faces
    )


def wait_for(condition: Callable[[], bool], timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


# --- drawing the frame ---------------------------------------------------------------------


def test_faces_are_boxed_in_the_colour_of_who_they_are():
    shown = annotate(
        scanning(
            FaceMark((10, 40, 40, 90), "Owner 0.80", Tone.OWNER),
            FaceMark((60, 40, 90, 90), "Someone else (owner 0.10)", Tone.OTHER),
            FaceMark(None, "no box: listed in the caption", Tone.SAMPLE),
        )
    )
    assert (shown[60, 10] == bgr(Tone.OWNER)).all()  # left edges, below the label tags
    assert (shown[60, 60] == bgr(Tone.OTHER)).all()


def test_the_robots_frame_is_never_drawn_on():
    view = scanning(FaceMark((10, 40, 40, 90), "Owner 0.80", Tone.OWNER))
    annotate(view)
    assert view.image.max() == 0


def test_once_the_step_ends_the_window_shows_no_frame_at_all():
    scene = (17, 140, 99)  # a colour the window never draws itself
    shot = Frame(image=np.full((100, 100, 3), scene, np.uint8), captured_at=T0)
    feed = LiveFeed(lambda: True)
    x, y, w, h = CAMERA
    panel = (x, y, x + w, y + h)
    with feed.activity("Scanning"):
        feed.face(shot, [FaceMark((10, 40, 40, 90), "Someone else", Tone.OTHER)])
        assert drawn(render(feed.snapshot()), panel, scene)
    canvas = render(feed.snapshot())
    assert not drawn(canvas, panel, scene)  # not even dimmed
    assert not drawn(canvas, panel, bgr(Tone.OTHER))


def test_labels_are_drawn_in_ascii():
    assert ascii_text("insightface · the owner if similarity ≥ 0.40") == (
        "insightface - the owner if similarity >= 0.40"
    )


# --- the pipe format -----------------------------------------------------------------------


def test_a_view_round_trips_through_the_pipe():
    view = LiveView(
        title="Reminder #1: listening",
        detail="threshold 0.35",
        active=True,
        step=3,
        image=np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3),
        faces=(FaceMark((1.0, 2.0, 3.0, 4.0), "Owner 0.80", Tone.OWNER),),
        note="looking left",
        levels=(Level(-20.0, True), Level(-55.5, False)),
        speech=0.9,
        speech_threshold=0.5,
        voices=(VoiceMark(2.0, "Owner 0.91", Tone.OWNER),),
        sound_step=3,
    )
    stream = io.BytesIO(wire.encode(view, with_image=True) + wire.encode(view, with_image=False))
    first = wire.read(stream)
    second = wire.read(stream, first)
    for got in (first, second):
        assert got.faces == view.faces and got.levels == view.levels
        assert got.voices == view.voices and got.microphone_live
        assert (got.title, got.detail, got.note, got.speech) == (
            view.title,
            view.detail,
            view.note,
            view.speech,
        )
        assert (got.image == view.image).all()
    assert second.image is first.image  # not sent again: the window keeps the frame it has
    assert wire.read(stream) is None


def test_a_cut_off_message_reads_as_the_end():
    message = wire.encode(scanning(), with_image=True)
    assert wire.read(io.BytesIO(message[:-1])) is None


# --- when the window opens -----------------------------------------------------------------


def test_the_window_opens_when_a_step_starts_and_gets_each_new_view_once():
    feed, windows = LiveFeed(lambda: True), Windows()
    window = DesktopWindow(feed, windows)
    window.tick()
    assert windows.opened == []  # nothing has happened yet
    with feed.activity("Scanning"):
        feed.face(frame(), [FaceMark(None, "Owner 0.80", Tone.OWNER)])
        window.tick()
        window.tick()  # nothing new: nothing sent
        feed.voice(2.0, "Owner 0.70", Tone.OWNER)
        window.tick()
    window.tick()
    (opened,) = windows.opened
    assert [v.active for v in opened.views] == [True, True, False]
    assert opened.frames_sent == 1  # the frame went once; later views reuse it
    assert opened.views[1].faces[0].label == "Owner 0.80"
    assert (opened.views[-1].image, opened.views[-1].faces) == (None, ())  # gone with the step
    window.close()
    assert opened.closed


def test_a_short_step_between_two_ticks_still_opens_the_window():
    feed, windows = LiveFeed(lambda: True), Windows()
    window = DesktopWindow(feed, windows)
    with feed.activity("Scanning"):
        feed.face(frame(), [])
    window.tick()
    assert windows.last.views[0].title == "Scanning"


def test_a_window_closed_by_the_user_opens_again_at_the_next_step():
    feed, windows = LiveFeed(lambda: True), Windows()
    window = DesktopWindow(feed, windows)
    with feed.activity("Listening"):
        window.tick()
        windows.last.alive = False  # closed with q
        feed.voice(2.0, "Owner", Tone.OWNER)
        window.tick()
    assert len(windows.opened) == 1
    with feed.activity("Scanning"):
        window.tick()
    assert len(windows.opened) == 2 and windows.last.views[0].title == "Scanning"


def test_switching_the_live_view_off_closes_the_window():
    enabled = True
    feed, windows = LiveFeed(lambda: enabled), Windows()
    window = DesktopWindow(feed, windows)
    with feed.activity("Listening"):
        window.tick()
    enabled = False
    window.tick()
    assert windows.last.closed
    enabled = True
    with feed.activity("Scanning"):  # counted afresh, and still opens
        window.tick()
    assert len(windows.opened) == 2


def test_a_window_that_cannot_open_never_stops_the_robot():
    attempts = []

    def no_display() -> WindowProcess:
        attempts.append(1)
        raise OSError("no display")

    feed = LiveFeed(lambda: True)
    window = DesktopWindow(feed, no_display)
    with feed.activity("Scanning"):
        window.tick()
        window.tick()  # not retried during the same step
    assert len(attempts) == 1


async def test_the_window_closes_when_the_robot_stops():
    feed, windows = LiveFeed(lambda: True), Windows()
    window = DesktopWindow(feed, windows)
    with feed.activity("Scanning"):
        task = asyncio.create_task(window.run())
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert windows.last.closed


# --- the window process --------------------------------------------------------------------

COUNT_MESSAGES = """
import sys
from pasr.live import wire
count, view = 0, None
while (view := wire.read(sys.stdin.buffer, view)) is not None:
    count += 1
open(sys.argv[1], "w").write(str(count))
"""


def test_the_window_gets_every_view_and_ends_with_the_pipe(tmp_path):
    out = tmp_path / "count"
    window = WindowProcess([sys.executable, "-c", COUNT_MESSAGES, str(out)])
    for _ in range(3):
        window.send(wire.encode(scanning(), with_image=True))
    window.close()
    wait_for(lambda: not window.alive)
    assert out.read_text() == "3"


def test_a_window_closed_by_the_user_is_no_longer_alive():
    window = WindowProcess([sys.executable, "-c", "pass"])
    wait_for(lambda: not window.alive)
    window.send(wire.encode(scanning(), with_image=False))  # nobody reads it: dropped quietly
    window.close()


def test_a_stuck_window_never_holds_up_the_robot(monkeypatch):
    monkeypatch.setattr(desktop, "MAX_PENDING_BYTES", 1_000_000)
    window = WindowProcess([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        message = wire.encode(
            LiveView(image=np.zeros((200, 333, 3), np.uint8)), with_image=True
        )  # about 200 kB
        for _ in range(100):  # 20 MB, far more than the pipe holds
            window.send(message)
        assert window._pending_bytes <= 1_000_000  # the oldest views were dropped
    finally:
        window._process.kill()


# --- how the window draws ------------------------------------------------------------------


def drawn(canvas: np.ndarray, region: tuple[int, int, int, int], color) -> bool:
    x1, y1, x2, y2 = region
    return bool((canvas[y1:y2, x1:x2] == color).all(axis=-1).any())


def test_the_window_draws_before_anything_arrives():
    assert render(LiveView()).shape == (HEIGHT, WIDTH, 3)


def test_the_window_shows_the_frame_with_its_boxes():
    canvas = render(scanning(FaceMark((10, 40, 40, 90), "Owner 0.80", Tone.OWNER)))
    x, y, _, _ = CAMERA
    left = x + 80  # the 100 x 100 frame is scaled 4.8 times to 480 x 480, centred in the panel
    assert drawn(canvas, (left + 40, y + 250, left + 56, y + 400), bgr(Tone.OWNER))


def test_the_window_lists_voices_in_their_colour_and_dims_a_microphone_that_is_off():
    listening = LiveView(
        title="Listening",
        active=True,
        step=1,
        voices=(VoiceMark(2.0, "Someone else (owner 0.10)", Tone.OTHER),),
        sound_step=1,
    )
    x, y, w, h = MICROPHONE
    assert drawn(render(listening), (x, y, x + w, y + h), bgr(Tone.OTHER))
    earlier = LiveView(step=2, voices=listening.voices, sound_step=1)
    assert not drawn(render(earlier), (x, y, x + w, y + h), bgr(Tone.OTHER))
