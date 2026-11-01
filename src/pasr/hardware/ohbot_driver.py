"""One process-wide handle on the ``ohbot`` library.

The API lives in the submodule ``ohbot.ohbot`` (the package's ``__init__`` is empty). The library
is not thread-safe and importing it has side effects: it creates ``ohbotData/`` in the current
working directory and probes the serial ports. This module is therefore the only place that
imports it , inside a worker thread, under one lock, after switching the process to
``OHBOT_WORK_DIR``. ``OhbotHead`` and ``OhbotSpeaker`` share the driver so a lip-sync move can
never interleave with a scan move.
"""

from __future__ import annotations

import atexit
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pasr.domain.enums import Direction, Pose
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.speaker.output import device_player
from pasr.paths import OHBOT_WORK_DIR

logger = logging.getLogger(__name__)

HEADNOD, HEADTURN, EYETURN, LIDBLINK, TOPLIP, BOTTOMLIP, EYETILT = range(7)
"""Ohbot motor indices (positions 0–10)."""

DATA_DIR = Path("ohbotData")
"""The library's data folder, always addressed relative to the working directory."""

SPEECH_FILE = DATA_DIR / "ohbotspeech.wav"
"""Written by ``ohbot.say`` relative to the working directory. It holds the robot's own words ,
a reminder title , so the driver removes it after every utterance (docs/PRIVACY.md)."""

_SHELL_UNSAFE = re.compile(r"[\"'`$\;|&<>\n\r]")


@dataclass(frozen=True, slots=True)
class TurnPositions:
    """HEADTURN positions for the three scan directions; calibrate on the real head."""

    left: float
    front: float
    right: float

    def for_direction(self, direction: Direction) -> float:
        return {
            Direction.LEFT: self.left,
            Direction.FRONT: self.front,
            Direction.RIGHT: self.right,
        }[direction]


POSES: dict[Pose, dict[int, float]] = {
    Pose.ATTENTION: {HEADNOD: 6, EYETILT: 5, LIDBLINK: 10},
    Pose.REST: {HEADNOD: 4, EYETILT: 5, LIDBLINK: 7},
}


class _PortName(str):
    """ohbot 4.0.18's ``init(portName)`` hands ``portName`` to ``checkPort``, which opens
    ``portName[0]`` (written for a pyserial ``ListPortInfo``) , i.e. ``"/"`` for a plain string.
    Indexing this name at 0 returns the whole name, so an explicit port works."""

    __slots__ = ()

    def __getitem__(self, key: Any) -> Any:
        return str(self) if key == 0 else super().__getitem__(key)


def sanitise_speech(text: str) -> str:
    """The library hands text to macOS ``say`` through a shell string: drop what could break out."""
    return " ".join(_SHELL_UNSAFE.sub(" ", text).split())


class OhbotDriver:
    """Lazy import, init once, close once, one lock around every library call."""

    _shared: ClassVar[OhbotDriver | None] = None
    _shared_guard: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, port: str, work_dir: Path | None = None) -> None:
        self.port = port
        self.work_dir = work_dir or OHBOT_WORK_DIR
        self._lock = threading.Lock()
        self._lib: Any = None
        self._default_player: Any = None
        self._atexit_registered = False

    @classmethod
    def shared(cls, port: str) -> OhbotDriver:
        with cls._shared_guard:
            if cls._shared is None:
                cls._shared = cls(port)
            elif cls._shared.port != port:
                logger.warning("Ohbot driver already created for port %s", cls._shared.port)
            return cls._shared

    @property
    def started(self) -> bool:
        return self._lib is not None

    def ensure_started(self) -> None:
        """Blocking. Imports the library (which probes the ports) and checks the connection."""
        with self._lock:
            if self._lib is not None:
                return
            self._enter_work_dir()  # the import writes ohbotData/ into the CWD
            try:
                from ohbot import ohbot  # the import probes every *usb* port ("auto")
            except ImportError as exc:
                raise HardwareNotAvailableError(
                    "The ohbot library is not installed: uv sync"
                ) from exc
            except Exception as exc:  # the import itself talks to serial ports
                raise HardwareNotAvailableError(f"ohbot failed to start: {exc}") from exc
            if not getattr(ohbot, "connected", False) and self.port != "auto":
                ohbot.init(_PortName(self.port))
            elif self.port not in ("auto", getattr(ohbot, "port", self.port)):
                logger.warning("Ohbot found on %s, not on the configured %s", ohbot.port, self.port)
            if not getattr(ohbot, "connected", False):
                where = "any USB serial port" if self.port == "auto" else self.port
                raise HardwareNotAvailableError(
                    f"No Ohbot found on {where}; check the USB cable and hardware.ohbot.port"
                )
            self._lib = ohbot
            self._default_player = getattr(ohbot, "playsound", None)
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True

    def stop(self) -> None:
        """Blocking. Detaches the motors; idempotent."""
        with self._lock:
            lib, self._lib = self._lib, None
            if lib is None:
                return
            try:
                lib.close()
            except Exception:
                logger.warning("ohbot.close() failed", exc_info=True)
            self._remove_speech_file()

    def move(self, motor: int, position: float, speed: int = 5) -> None:
        with self._lock:
            self._require().move(motor, float(position), int(speed))

    def say(self, text: str, *, output_device: str | None = None) -> None:
        """Blocking; returns when the library estimates the speech has finished.

        The library plays the speech with its module-level ``playsound`` (``afplay``: the macOS
        default output). With ``output_device`` that function is swapped for one that plays on
        the named device; the speech generation and lip sync stay the library's.
        """
        with self._lock:
            lib = self._require()
            lib.playsound = device_player(output_device) if output_device else self._default_player
            # say() writes and reads ohbotData/ relative to the CWD on every call, but the
            # library creates that folder only once, at import.
            self._enter_work_dir()
            try:
                lib.say(sanitise_speech(text), untilDone=True, lipSync=True)
            finally:
                self._remove_speech_file()

    def _require(self) -> Any:
        if self._lib is None:
            raise HardwareNotAvailableError("Ohbot is not connected")
        return self._lib

    def _enter_work_dir(self) -> None:
        (self.work_dir / DATA_DIR).mkdir(parents=True, exist_ok=True)
        os.chdir(self.work_dir)

    def _remove_speech_file(self) -> None:
        (self.work_dir / SPEECH_FILE).unlink(missing_ok=True)
