"""Wire format between the PC and the Bangle.js consent app ``bangle/consent_app.js``
(docs/WATCH_PROTOCOL.md).

PC → watch: the Bangle's Bluetooth console evaluates each line as JavaScript, so a command is a
call of one of the app's globals, prefixed with ``\\x10`` (do not echo) and ended with a newline:

- ``consent("7","Say it out loud?",60)`` , the app answers ``CONSENT:7:YES`` or ``CONSENT:7:NO``,
  and sends nothing when nobody answers in time.
- ``notify("Reminder: Dentist");Bluetooth.println("NOTIFIED:8")`` , the app's ``notify`` sends
  nothing back, so the line itself confirms that it ran.
- ``Bluetooth.println("PONG:9:"+typeof consent)`` , the console is alive, and says whether the
  app is loaded (``function``) or not (``undefined``).

Watch → PC: those reply lines. Anything else on the console (prompts, errors) is ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

BLE_CHUNK_BYTES = 20
"""Bangle.js 1 accepts 20-byte writes (default BLE MTU)."""
MAX_TEXT = 160

ReplyType = Literal["answer", "ack", "pong"]


@dataclass(frozen=True, slots=True)
class WatchReply:
    type: ReplyType
    id: int
    value: str | None = None
    """``yes``/``no`` for an answer; the type of the app's ``consent`` for a pong."""


def _js(text: str) -> str:
    """A JavaScript string literal (JSON, ASCII-only: Espruino understands \\u escapes)."""
    return json.dumps(text, ensure_ascii=True)


def _line(code: str) -> bytes:
    return b"\x10" + code.encode("ascii") + b"\n"


def consent_command(request_id: int, text: str, timeout_s: float) -> bytes:
    return _line(f"consent({_js(str(request_id))},{_js(text[:MAX_TEXT])},{round(timeout_s)})")


def notify_command(request_id: int, text: str) -> bytes:
    return _line(f'notify({_js(text[:MAX_TEXT])});Bluetooth.println("NOTIFIED:{request_id}")')


def ping_command(request_id: int) -> bytes:
    return _line(f'Bluetooth.println("PONG:{request_id}:"+typeof consent)')


def chunks(data: bytes, size: int = BLE_CHUNK_BYTES) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


def parse_reply(line: str) -> WatchReply | None:
    kind, _, rest = line.strip().partition(":")
    request, _, value = rest.partition(":")
    if not request.isdigit():
        return None
    request_id = int(request)
    if kind == "CONSENT" and value in ("YES", "NO"):
        return WatchReply("answer", request_id, value.lower())
    if kind == "NOTIFIED" and not value:
        return WatchReply("ack", request_id)
    if kind == "PONG" and value:
        return WatchReply("pong", request_id, value)
    return None


class LineDecoder:
    """Reassembles newline-terminated lines from BLE notification fragments."""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> list[str]:
        self._buffer += data
        *lines, self._buffer = self._buffer.split(b"\n")
        return [line.decode("utf-8", errors="replace").rstrip("\r") for line in lines]
