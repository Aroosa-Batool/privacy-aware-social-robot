"""What goes wrong while the robot runs, for the dashboard to show as toasts.

Every warning and error the robot logs becomes a notice, and so does an error that nothing
caught on the robot's event loop, so no problem is only in the terminal. A log call with
``extra={"toast": True}`` adds good news (a device that came back); one with
``extra={"toast": False}`` stays in the terminal, for a failure the dashboard shows its own way.
The dashboard's own messages are toasts already.

Notices are kept in memory, the last ``KEPT``; the event log stays labels and numbers only
(docs/PRIVACY.md).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

KEPT = 50
ROBOT = "pasr"
DASHBOARD = "pasr.dashboard"
UNKNOWN = "an unknown error occurred"

_ids = itertools.count(1)  # across runtimes, so a restarted robot's notices are new ones


def describe(exc: BaseException) -> str:
    """An error in words: its message, or that it is unknown when it carries none."""
    return str(exc).strip() or f"{UNKNOWN} ({type(exc).__name__})"


def sentence(text: str) -> str:
    text = text.strip() or UNKNOWN
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else f"{text}."


@dataclass(frozen=True, slots=True)
class Notice:
    id: int
    at: float
    """``time.time()`` when it happened."""
    kind: Literal["error", "warning", "info"]
    message: str


class Notices(logging.Handler):
    """Collects notices from the robot's log while attached."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self._kept: deque[Notice] = deque(maxlen=KEPT)
        self._level = logging.NOTSET

    def attach(self) -> None:
        robot = logging.getLogger(ROBOT)
        self._level = robot.level
        if robot.getEffectiveLevel() > logging.INFO:  # so good news is not dropped unseen
            robot.setLevel(logging.INFO)
        robot.addHandler(self)

    def detach(self) -> None:
        robot = logging.getLogger(ROBOT)
        robot.removeHandler(self)
        robot.setLevel(self._level)

    def since(self, after: int) -> list[Notice]:
        """The notices after the one numbered ``after``, oldest first."""
        self.acquire()
        try:
            return [notice for notice in self._kept if notice.id > after]
        finally:
            self.release()

    def emit(self, record: logging.LogRecord) -> None:
        toast = getattr(record, "toast", None)
        if toast is False or record.name.startswith(DASHBOARD):
            return
        if record.levelno < logging.WARNING and not toast:
            return
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            message = f"{message}: {describe(record.exc_info[1])}"
        kind: Literal["error", "warning", "info"] = (
            "error"
            if record.levelno >= logging.ERROR
            else "warning"
            if record.levelno >= logging.WARNING
            else "info"
        )
        self._kept.append(Notice(next(_ids), record.created, kind, sentence(message)))


def on_loop_error(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """The robot's event loop's handler for an error nothing else caught: logged, so it also
    shows as a toast."""
    exc = context.get("exception")
    if isinstance(exc, BaseException):
        logger.error("something in the robot failed", exc_info=exc)
    else:
        logger.error("%s (%s)", UNKNOWN, context.get("message") or "no details")
