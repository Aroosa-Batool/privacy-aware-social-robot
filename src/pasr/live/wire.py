"""The live view sent to its desktop window, over the window process's stdin.

Each message is a length prefix, a JSON header and, when the frame changed, the frame's bytes.
They exist only in memory and in the pipe; neither side writes them anywhere.
"""

from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

import numpy as np

from pasr.live.feed import Box, FaceMark, Level, LiveView, Tone, VoiceMark

PREFIX = struct.Struct("!II")
"""Header length, payload length."""


def encode(view: LiveView, *, with_image: bool) -> bytes:
    """``view`` as one message; without ``with_image`` the window keeps the frame it has."""
    image = view.image if with_image else None
    fields: dict[str, Any] = {
        "title": view.title,
        "detail": view.detail,
        "active": view.active,
        "step": view.step,
        "faces": [[face.box, face.label, face.tone] for face in view.faces],
        "note": view.note,
        "levels": [[level.db, level.speech] for level in view.levels],
        "speech": view.speech,
        "speech_threshold": view.speech_threshold,
        "voices": [[voice.seconds, voice.label, voice.tone] for voice in view.voices],
        "sound_step": view.sound_step,
        "image": "same" if not with_image else list(image.shape) if image is not None else None,
    }
    header = json.dumps(fields).encode()
    payload = image.tobytes() if image is not None else b""
    return PREFIX.pack(len(header), len(payload)) + header + payload


def read(stream: BinaryIO, previous: LiveView | None = None) -> LiveView | None:
    """The next view, or ``None`` once the robot has closed the pipe."""
    prefix = _read_exactly(stream, PREFIX.size)
    if prefix is None:
        return None
    header_size, payload_size = PREFIX.unpack(prefix)
    header = _read_exactly(stream, header_size)
    payload = _read_exactly(stream, payload_size)
    if header is None or payload is None:
        return None
    fields = json.loads(header)
    shape = fields["image"]
    if shape == "same":
        image = previous.image if previous is not None else None
    elif shape is None:
        image = None
    else:
        image = np.frombuffer(payload, np.uint8).reshape(shape)
    return LiveView(
        title=fields["title"],
        detail=fields["detail"],
        active=fields["active"],
        step=fields["step"],
        image=image,
        faces=tuple(FaceMark(_box(box), label, Tone(tone)) for box, label, tone in fields["faces"]),
        note=fields["note"],
        levels=tuple(Level(db, speech) for db, speech in fields["levels"]),
        speech=fields["speech"],
        speech_threshold=fields["speech_threshold"],
        voices=tuple(
            VoiceMark(seconds, label, Tone(tone)) for seconds, label, tone in fields["voices"]
        ),
        sound_step=fields["sound_step"],
    )


def _box(values: list[float] | None) -> Box | None:
    if values is None:
        return None
    x1, y1, x2, y2 = values
    return x1, y1, x2, y2


def _read_exactly(stream: BinaryIO, size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            return None
        data += chunk
    return bytes(data)
