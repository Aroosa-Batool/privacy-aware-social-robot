"""Device interfaces. All methods are async; real devices run blocking library calls in a
thread pool so the event loop (scheduler, dashboard snapshots) never stalls."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol

from pasr.domain.enums import Direction, Pose, WatchAnswer
from pasr.domain.media import AudioChunk, Frame


class HardwareNotAvailableError(RuntimeError):
    """A real device adapter that is not built yet, or a device that cannot be reached."""


class RobotHead(Protocol):
    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def look(self, direction: Direction, speed: int = 5) -> None: ...

    async def nudge(self, turn: float, nod: float, speed: int = 5) -> tuple[float, float]:
        """Turn by ``turn`` and nod by ``nod`` motor units from where the head points, within
        the motors' range; returns how far it actually turned and nodded. ``look`` turns it
        back; the nod stays until undone or until the next ``pose``."""
        ...

    async def pose(self, pose: Pose) -> None: ...

    async def blink(self) -> None: ...


class Speaker(Protocol):
    async def say(self, text: str) -> None:
        """Speak and return when finished."""
        ...


class Camera(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def grab(self) -> Frame:
        """One frame, kept in memory only."""
        ...


class Microphone(Protocol):
    def stream(self) -> AsyncGenerator[AudioChunk, None]:
        """Endless stream of mono float32 chunks. Close it (``contextlib.aclosing``) when done."""
        ...


class Watch(Protocol):
    app_missing: bool
    """The watch answered, but its consent app is not loaded."""

    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def ping(self) -> bool:
        """True when the watch answers and its consent app is loaded."""
        ...

    async def prompt(self, text: str, timeout_s: float) -> WatchAnswer:
        """Ask a yes/no question; ``TIMEOUT`` if the owner does not answer in time."""
        ...

    async def notify(self, text: str) -> None: ...
