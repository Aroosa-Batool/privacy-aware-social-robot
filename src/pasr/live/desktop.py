"""The live view in a desktop window on the laptop, whether the robot runs from the dashboard
or a terminal (``pasr run``, ``setup``, ``calibrate``).

The window is a separate process (``pasr.live.window``): macOS draws windows only on a main
thread, the dashboard runs the robot on a background thread, and an in-process window would
stall the robot's event loop whenever it is dragged. Views go to it through a pipe, in memory.
The robot never waits for the window: a feeder thread writes to the pipe and drops the oldest
messages when the window falls behind.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Sequence
from typing import Protocol

from pasr.live import wire
from pasr.live.feed import LiveFeed, LiveView

logger = logging.getLogger(__name__)

WINDOW_COMMAND = (sys.executable, "-m", "pasr.live.window")
MAX_PENDING_BYTES = 32 * 1024 * 1024
"""Unsent messages kept while the window falls behind; older ones are dropped."""


class Viewer(Protocol):
    @property
    def alive(self) -> bool: ...

    def send(self, message: bytes) -> None: ...

    def close(self) -> None: ...


class DesktopWindow:
    """Sends the live view to a window at most every ``INTERVAL_S``. The window opens when a
    listening, scanning, enrolment or calibration step starts; closed by the user, it opens
    again at the next step. Nothing opens while ``live_view.enabled`` is off."""

    INTERVAL_S = 0.1

    def __init__(self, feed: LiveFeed, open_window: Callable[[], Viewer] | None = None) -> None:
        self._feed = feed
        self._open_window = open_window or WindowProcess
        self._window: Viewer | None = None
        self._sent: LiveView | None = None
        self._closed_at_step = 0
        """Open again only for a later step than this one."""

    async def run(self) -> None:
        """Until cancelled; then the window closes."""
        try:
            while True:
                self.tick()
                await asyncio.sleep(self.INTERVAL_S)
        finally:
            self.close()

    def tick(self) -> None:
        view = self._feed.snapshot()
        if view is None:  # the live view is off (and counts steps afresh once back on)
            self.close()
            self._closed_at_step = 0
            return
        window = self._window
        if window is not None and not window.alive:  # closed by the user
            self._window = window = None
            self._closed_at_step = view.step
        if window is None:
            if view.step <= self._closed_at_step:
                return
            try:
                window = self._window = self._open_window()
            except Exception:  # the window is a convenience: the robot carries on without it
                logger.exception("could not open the live view window")
                self._closed_at_step = view.step
                return
            self._sent = None
        sent = self._sent
        if view is sent:
            return
        new_image = sent is None or view.image is not sent.image
        window.send(wire.encode(view, with_image=new_image))
        self._sent = view

    def close(self) -> None:
        window, self._window = self._window, None
        if window is not None:
            window.close()


class WindowProcess:
    """The window as a child process, fed by a thread. It runs in its own session, so Ctrl+C
    in the terminal stops the robot, which then closes the window."""

    def __init__(self, command: Sequence[str] = WINDOW_COMMAND) -> None:
        self._process = subprocess.Popen(
            list(command), stdin=subprocess.PIPE, start_new_session=True
        )
        self._pending: deque[bytes] = deque()
        self._pending_bytes = 0
        self._closing = False
        self._wake = threading.Condition()
        self._thread = threading.Thread(target=self._feed, name="pasr-live-window", daemon=True)
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and self._process.poll() is None

    def send(self, message: bytes) -> None:
        with self._wake:
            self._pending.append(message)
            self._pending_bytes += len(message)
            while self._pending_bytes > MAX_PENDING_BYTES and len(self._pending) > 1:
                self._pending_bytes -= len(self._pending.popleft())
            self._wake.notify()

    def close(self) -> None:
        """Close the pipe once the pending messages are sent, which ends the window; returns
        at once."""
        with self._wake:
            self._closing = True
            self._wake.notify()

    def _feed(self) -> None:
        stdin = self._process.stdin
        assert stdin is not None
        try:
            while True:
                with self._wake:
                    while not self._pending and not self._closing:
                        self._wake.wait()
                    if not self._pending:  # closing, and everything is sent
                        break
                    message = self._pending.popleft()
                    self._pending_bytes -= len(message)
                stdin.write(message)
                stdin.flush()
        except (OSError, ValueError):
            pass  # the window was closed
        finally:
            with contextlib.suppress(OSError):
                stdin.close()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
