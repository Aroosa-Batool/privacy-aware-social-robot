"""The live view's desktop window, run as ``python -m pasr.live.window`` by
``pasr.live.desktop`` (whether the robot runs from the dashboard or a terminal).

It draws the latest view it is sent: the analysed camera frame with its faces boxed and
labelled, the microphone level and the latest voice matches. Everything stays in memory. It
closes when the robot closes the pipe, or with q, Esc or the close button; the robot opens it
again at its next listening, scanning, enrolment or calibration step.
"""

from __future__ import annotations

import contextlib
import sys
import threading

import cv2
import numpy as np
import numpy.typing as npt

from pasr.live import wire
from pasr.live.feed import FLOOR_DB, LEVELS, LiveView, Tone, loudness

WINDOW = "PASR live view"
REFRESH_MS = 40
WIDTH, HEIGHT = 1120, 650
CAMERA = (16, 88, 640, 480)
MICROPHONE = (672, 88, 432, 480)
"""Panels as (x, y, width, height)."""

Color = tuple[int, int, int]  # BGR
Image = npt.NDArray[np.uint8]
Region = tuple[int, int, int, int]
BACKGROUND: Color = (28, 28, 28)
PANEL: Color = (44, 44, 44)
TEXT: Color = (235, 235, 235)
DIM: Color = (150, 150, 150)
LIVE: Color = (60, 60, 230)
IDLE: Color = (110, 110, 110)
SPEECH: Color = (183, 194, 195)
QUIET: Color = (78, 81, 82)
INK: Color = (11, 11, 11)
"""Text on the coloured face tags."""
TONES: dict[Tone, tuple[str, str]] = {
    Tone.OWNER: ("Owner", "#2a78d6"),
    Tone.OTHER: ("Someone else", "#eb6834"),
    Tone.SAMPLE: ("Enrolment sample", "#1baf7a"),
    Tone.IGNORED: ("Not used", "#8a8984"),
}
"""Legend name and colour. Blue, orange and aqua stay apart for every type of colour vision,
and every box and row also carries a text label; a remembered bystander shares the orange of
'someone else' and is named by the label."""
ASCII = str.maketrans({"·": "-", "≥": ">=", "…": "...", ",": "-", "–": "-"})


def bgr(tone: Tone) -> Color:
    value = TONES[tone][1]
    red, green, blue = (int(value[i : i + 2], 16) for i in (1, 3, 5))
    return blue, green, red


def ascii_text(text: str) -> str:
    """OpenCV's font has ASCII only."""
    return text.translate(ASCII).encode("ascii", "replace").decode()


# --- the camera frame ----------------------------------------------------------------------


def annotate(view: LiveView) -> Image:
    """The current step's frame with each face boxed and labelled."""
    assert view.image is not None
    image = view.image.copy()
    thickness = max(2, image.shape[1] // 320)
    scale = max(0.5, image.shape[1] / 1280)
    for face in view.faces:
        if face.box is None:  # the plugin gives no box: the caption lists the label
            continue
        color = bgr(face.tone)
        x1, y1, x2, y2 = (round(v) for v in face.box)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
        _tag(image, face.label, x1, y1, color, scale)
    return image


def _tag(image: Image, label: str, x: int, y: int, color: Color, scale: float) -> None:
    """A filled label above (x, y), or below it when there is no room above."""
    text = ascii_text(label)
    (width, height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    pad = 5
    top = y - height - 2 * pad if y - height - 2 * pad >= 0 else y
    cv2.rectangle(image, (x, top), (x + width + 2 * pad, top + height + 2 * pad), color, -1)
    cv2.putText(
        image,
        text,
        (x + pad, top + height + pad),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        INK,
        1,
        cv2.LINE_AA,
    )


# --- the whole window ----------------------------------------------------------------------


def render(view: LiveView) -> Image:
    canvas = np.full((HEIGHT, WIDTH, 3), BACKGROUND, np.uint8)
    _header(canvas, view)
    _camera(canvas, view)
    _microphone(canvas, view)
    _legend(canvas)
    return canvas


def _text(
    canvas: Image,
    text: str,
    x: int,
    y: int,
    *,
    scale: float = 0.5,
    color: Color = TEXT,
) -> None:
    cv2.putText(
        canvas,
        ascii_text(text),
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        1,
        cv2.LINE_AA,
    )


def _centered(canvas: Image, lines: list[str], region: Region) -> None:
    x, y, w, h = region
    top = y + h // 2 - 14 * (len(lines) - 1)
    for row, line in enumerate(lines):
        scale = 0.7 if row == 0 else 0.5
        (width, _), _ = cv2.getTextSize(ascii_text(line), cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        _text(canvas, line, x + (w - width) // 2, top + 28 * row, scale=scale)


def _switched_off(canvas: Image, region: Region, lines: list[str]) -> None:
    """Dim a panel whose sensor is off now; its content is from an earlier step."""
    x, y, w, h = region
    canvas[y : y + h, x : x + w] = (canvas[y : y + h, x : x + w] * 0.3).astype(np.uint8)
    _centered(canvas, lines, region)


def _header(canvas: Image, view: LiveView) -> None:
    cv2.rectangle(canvas, (0, 0), (WIDTH, 64), PANEL, -1)
    _text(canvas, view.title, 16, 28, scale=0.7)
    _text(canvas, view.detail, 16, 52, scale=0.45, color=DIM)
    status, color = ("LIVE", LIVE) if view.active else ("IDLE", IDLE)
    cv2.circle(canvas, (WIDTH - 86, 30), 8, color, -1)
    _text(canvas, status, WIDTH - 70, 36, scale=0.6)


def _faces(view: LiveView) -> str:
    count = len(view.faces)
    return "no face" if not count else f"{count} face{'s' if count > 1 else ''}"


def _camera(canvas: Image, view: LiveView) -> None:
    x, y, w, h = CAMERA
    cv2.rectangle(canvas, (x, y), (x + w, y + h), PANEL, -1)
    _text(canvas, "Camera", x, y - 8, color=DIM)
    if view.image is None:  # between steps, and in steps without the camera: no frame at all
        _centered(canvas, ["Camera off"], CAMERA)
        return
    frame = annotate(view)
    scale = min(w / frame.shape[1], h / frame.shape[0])
    size = (max(1, round(frame.shape[1] * scale)), max(1, round(frame.shape[0] * scale)))
    left, top = x + (w - size[0]) // 2, y + (h - size[1]) // 2
    canvas[top : top + size[1], left : left + size[0]] = cv2.resize(frame, size)
    unboxed = [face.label for face in view.faces if face.box is None]
    caption = " - ".join(part for part in (view.note, _faces(view), *unboxed) if part)
    _text(canvas, caption, x, y + h + 26)


def _bar(
    canvas: Image, region: Region, fraction: float, color: Color, tick: float | None = None
) -> None:
    x, y, w, h = region
    cv2.rectangle(canvas, (x, y), (x + w, y + h), BACKGROUND, -1)
    filled = round(w * min(max(fraction, 0.0), 1.0))
    if filled:
        cv2.rectangle(canvas, (x, y), (x + filled, y + h), color, -1)
    if tick is not None:
        at = x + round(w * min(max(tick, 0.0), 1.0))
        cv2.line(canvas, (at, y - 4), (at, y + h + 4), TEXT, 2)


def _microphone(canvas: Image, view: LiveView) -> None:
    x, y, w, h = MICROPHONE
    cv2.rectangle(canvas, (x, y), (x + w, y + h), PANEL, -1)
    _text(canvas, "Microphone", x, y - 8, color=DIM)
    if view.sound_step < 0:
        _centered(canvas, ["Microphone off"], MICROPHONE)
        return
    left, width = x + 16, w - 32
    latest = view.levels[-1] if view.levels else None
    level = latest.db if latest else FLOOR_DB
    _text(canvas, f"Level {level:.0f} dB", left, y + 28)
    color = SPEECH if latest and latest.speech else QUIET
    _bar(canvas, (left, y + 38, width, 16), loudness(level), color)
    _text(
        canvas,
        f"Speech probability {view.speech:.2f} - speech from {view.speech_threshold:.2f}",
        left,
        y + 82,
    )
    color = SPEECH if view.speech >= view.speech_threshold else QUIET
    _bar(canvas, (left, y + 92, width, 16), view.speech, color, tick=view.speech_threshold)

    graph_top, graph_height = y + 140, 80
    _text(canvas, "The last few seconds", left, graph_top - 8, scale=0.45, color=DIM)
    step = width / LEVELS
    for index, sample in enumerate(view.levels):
        height = max(1, round(loudness(sample.db) * graph_height))
        bar_left = left + round(index * step)
        cv2.rectangle(
            canvas,
            (bar_left, graph_top + graph_height - height),
            (bar_left + max(1, round(step) - 1), graph_top + graph_height),
            SPEECH if sample.speech else QUIET,
            -1,
        )

    rows_top = y + 256
    _text(canvas, "Speech segments, newest first", left, rows_top, scale=0.45, color=DIM)
    if not view.voices:
        _text(canvas, "none yet", left, rows_top + 30, color=DIM)
    for row, voice in enumerate(view.voices):
        row_y = rows_top + 30 + 30 * row
        cv2.circle(canvas, (left + 6, row_y - 5), 6, bgr(voice.tone), -1)
        _text(canvas, f"{voice.seconds:4.1f} s   {voice.label}", left + 20, row_y)
    if not view.microphone_live:
        _switched_off(canvas, MICROPHONE, ["Microphone off", "Showing the last step"])


def _legend(canvas: Image) -> None:
    x, y = 16, HEIGHT - 20
    for tone, (name, _) in TONES.items():
        cv2.rectangle(canvas, (x, y - 12), (x + 14, y + 2), bgr(tone), -1)
        _text(canvas, name, x + 20, y, scale=0.45)
        (width, _), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        x += width + 44
    _text(canvas, "q or Esc: close", WIDTH - 140, y, scale=0.45, color=DIM)


def main() -> None:
    latest = [LiveView()]
    lock, ended = threading.Lock(), threading.Event()

    def read_views() -> None:
        view: LiveView | None = None
        while (view := wire.read(sys.stdin.buffer, view)) is not None:
            with lock:
                latest[0] = view
        ended.set()

    threading.Thread(target=read_views, name="pasr-live-read", daemon=True).start()
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    with contextlib.suppress(cv2.error, AttributeError):
        cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)
    shown = False
    while not ended.is_set():
        with lock:
            view = latest[0]
        cv2.imshow(WINDOW, render(view))
        key = cv2.waitKey(REFRESH_MS) & 0xFF
        visible = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) >= 1
        if key in (ord("q"), 27) or (shown and not visible):  # closed by the user
            break
        shown = shown or visible
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
