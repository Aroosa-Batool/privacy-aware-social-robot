"""Live-view stand-ins: a feed that records everything it was shown, not just the latest view,
and a desktop window that records what it was sent instead of drawing it."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Iterator, Sequence

from pasr.domain.media import AudioChunk, Frame
from pasr.live import wire
from pasr.live.feed import FaceMark, LiveFeed, LiveView, Tone, VoiceMark


class RecordingWindow:
    def __init__(self) -> None:
        self.views: list[LiveView] = []
        self.frames_sent = 0
        self.alive = True
        self.closed = False

    def send(self, message: bytes) -> None:
        view = wire.read(io.BytesIO(message), self.views[-1] if self.views else None)
        assert view is not None
        self.views.append(view)
        _, payload_size = wire.PREFIX.unpack(message[: wire.PREFIX.size])
        self.frames_sent += payload_size > 0

    def close(self) -> None:
        self.closed = True
        self.alive = False


class Windows:
    """Opens a fresh ``RecordingWindow`` each time it is asked for one."""

    def __init__(self) -> None:
        self.opened: list[RecordingWindow] = []

    def __call__(self) -> RecordingWindow:
        self.opened.append(RecordingWindow())
        return self.opened[-1]

    @property
    def last(self) -> RecordingWindow:
        return self.opened[-1]


class RecordingFeed(LiveFeed):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__(lambda: enabled)
        self.steps: list[str] = []
        self.details: list[str] = []
        self.faces: list[FaceMark] = []
        self.notes: list[str] = []
        self.voices: list[VoiceMark] = []
        self.chunks = 0

    @contextlib.contextmanager
    def activity(self, title: str, detail: str = "") -> Iterator[None]:
        with super().activity(title, detail):
            if self._showing():
                self.steps.append(title)
                self.details.append(detail)
            yield

    def face(self, frame: Frame, marks: Sequence[FaceMark], *, note: str = "") -> None:
        super().face(frame, marks, note=note)
        if self._showing():
            self.faces += marks
            self.notes.append(note)

    def audio(self, chunk: AudioChunk, speech: float, threshold: float) -> None:
        super().audio(chunk, speech, threshold)
        if self._showing():
            self.chunks += 1

    def voice(self, seconds: float, label: str, tone: Tone) -> None:
        super().voice(seconds, label, tone)
        if self._showing():
            self.voices.append(VoiceMark(round(seconds, 1), label, tone))

    def _showing(self) -> bool:
        view = self.snapshot()
        return view is not None and view.active
