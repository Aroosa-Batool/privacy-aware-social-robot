"""What the robot senses while it listens, scans, enrols or calibrates, kept in memory for the
dashboard's live view (``live_view.enabled``, off by default).

Only the latest analysed frame, a few seconds of microphone levels and the last few voice
matches are kept, and only while the setting is on. Nothing is written anywhere, and reminder
titles are never recorded. Only what happens inside ``activity`` is kept, and the frame goes
when its step ends, so the view never shows the camera outside those steps, not even a last
frame.

The feed is updated on the runtime's event loop. Each update replaces an immutable
``LiveView``, which the dashboard reads through ``snapshot`` (``RuntimeHandle.call_sync``).
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from pasr.domain.media import AudioChunk, Frame

MAX_FRAME_WIDTH = 960
"""Wider frames are shrunk before they are kept."""
LEVELS = 100
"""Microphone chunks in the level history (about 3 s at 32 ms per chunk)."""
VOICES = 6
"""Speech segments listed."""
FLOOR_DB = -60.0
"""The quietest level the views draw."""

Box = tuple[float, float, float, float]


def loudness(db: float) -> float:
    """A level in dBFS as a fraction of the drawn range."""
    return min(max((db - FLOOR_DB) / -FLOOR_DB, 0.0), 1.0)


class Tone(StrEnum):
    """What a face box or voice row means; the dashboard picks its colour."""

    OWNER = "owner"
    """The owner (in calibration: a sample at or above the current threshold)."""
    OTHER = "other"
    """Someone else; the label names a remembered bystander (in calibration: a sample below the
    current threshold)."""
    SAMPLE = "sample"
    """An enrolment sample."""
    IGNORED = "ignored"
    """Not used (too short, several faces)."""


@dataclass(frozen=True, slots=True)
class FaceMark:
    box: Box | None
    """(x1, y1, x2, y2) in pixels of the frame; ``None`` if the plugin gives no box."""
    label: str
    tone: Tone


@dataclass(frozen=True, slots=True)
class VoiceMark:
    seconds: float
    label: str
    tone: Tone


@dataclass(frozen=True, slots=True)
class Level:
    db: float
    """Loudness in dBFS."""
    speech: bool


@dataclass(frozen=True, slots=True, eq=False)
class LiveView:
    """What the live view shows. ``step`` counts the steps, so the microphone panel can tell
    whether its content is from the current one or an earlier one."""

    title: str = "Waiting for the robot"
    detail: str = ""
    active: bool = False
    """The robot is listening, scanning, enrolling or calibrating now."""
    step: int = 0
    image: npt.NDArray[np.uint8] | None = None
    """The latest frame analysed in the current step (BGR, at most ``MAX_FRAME_WIDTH`` wide);
    ``None`` between steps. Never modify it."""
    faces: tuple[FaceMark, ...] = ()
    note: str = ""
    levels: tuple[Level, ...] = ()
    speech: float = 0.0
    """Speech probability of the latest chunk."""
    speech_threshold: float = 0.5
    voices: tuple[VoiceMark, ...] = ()
    """Newest first."""
    sound_step: int = -1

    @property
    def microphone_live(self) -> bool:
        return self.active and self.sound_step == self.step


class LiveFeed:
    """Called on the runtime's event loop only. ``enabled`` is read as each step starts and on
    every ``snapshot``, so switching the live view off drops what it holds at once."""

    def __init__(self, enabled: Callable[[], bool]) -> None:
        self._enabled = enabled
        self._view = LiveView()

    def snapshot(self) -> LiveView | None:
        """What to show, or ``None`` while the live view is off."""
        if not self._enabled():
            self._view = LiveView()
            return None
        return self._view

    @contextlib.contextmanager
    def activity(self, title: str, detail: str = "") -> Iterator[None]:
        """Keep what is sensed inside the block, shown under ``title``."""
        if self._enabled():
            self._view = replace(
                self._view, title=title, detail=detail, active=True, step=self._view.step + 1
            )
        else:
            self._view = LiveView()
        try:
            yield
        finally:  # the frame and its marks go with the step: no last frame stays on show
            self._view = replace(self._view, active=False, image=None, faces=(), note="")

    def face(self, frame: Frame, marks: Sequence[FaceMark], *, note: str = "") -> None:
        """A frame the robot analysed, with what it recognised in it."""
        view = self._view
        if not view.active:
            return
        step = max(1, math.ceil(frame.image.shape[1] / MAX_FRAME_WIDTH))
        faces = tuple(
            replace(mark, box=_scaled(mark.box, 1 / step)) if mark.box else mark for mark in marks
        )
        self._view = replace(
            view, image=np.ascontiguousarray(frame.image[::step, ::step]), faces=faces, note=note
        )

    def audio(self, chunk: AudioChunk, speech: float, threshold: float) -> None:
        """Loudness and speech probability of one microphone chunk."""
        view = self._view
        if not view.active:
            return
        samples = chunk.samples
        rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
        level = Level(round(20 * math.log10(max(rms, 1e-6)), 1), speech >= threshold)
        levels, voices = self._sound(view)
        self._view = replace(
            view,
            levels=(*levels, level)[-LEVELS:],
            speech=round(float(speech), 3),
            speech_threshold=threshold,
            voices=voices,
            sound_step=view.step,
        )

    def voice(self, seconds: float, label: str, tone: Tone) -> None:
        """A speech segment and what the robot made of it."""
        view = self._view
        if not view.active:
            return
        levels, voices = self._sound(view)
        mark = VoiceMark(round(seconds, 1), label, tone)
        self._view = replace(
            view, levels=levels, voices=(mark, *voices)[:VOICES], sound_step=view.step
        )

    def clear(self) -> None:
        self._view = LiveView()

    @staticmethod
    def _sound(view: LiveView) -> tuple[tuple[Level, ...], tuple[VoiceMark, ...]]:
        """The microphone history to extend: empty when a new step starts using it."""
        if view.sound_step != view.step:
            return (), ()
        return view.levels, view.voices


def _scaled(box: Box, scale: float) -> Box:
    x1, y1, x2, y2 = (round(v * scale, 1) for v in box)
    return x1, y1, x2, y2
