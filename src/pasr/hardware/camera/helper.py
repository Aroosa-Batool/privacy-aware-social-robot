"""The camera in a process of its own: ``python -m pasr.hardware.camera.helper INDEX WIDTH
HEIGHT WARMUP STALL [NAME]``. It opens the camera, answers each request on stdin with a frame on
stdout, and releases the camera when stdin closes (also when the robot's process ends). With a
NAME, it opens the first camera whose name contains it instead of the one at INDEX: indices
shift when an iPhone or another camera comes and goes, and a missing head camera would
otherwise leave the laptop's own camera at its index.

Why a process: macOS gives a process its cameras once. A camera that drops off USB and comes
back a moment later (its cable tugged as the head turns) stays dead in a process that had it
open, for as long as that process runs; a new process finds it again. So the robot reconnects a
camera that stopped sending frames by starting a new helper (ADR 0010). This module is the only
code that opens a camera through OpenCV.

Each message is a length prefix, a JSON header and, for a frame, its bytes. Frames exist only
in memory and in the pipe; neither side writes them anywhere.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import os
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal

import numpy as np

from pasr.hardware.protocols import HardwareNotAvailableError

COMMAND = (sys.executable, "-m", "pasr.hardware.camera.helper")
GRAB = b"g"
PREFIX = struct.Struct("!II")
"""Header length, payload length."""
RETRY_PAUSE = 0.05
"""Pause between failed reads; AVFoundation's ``read`` itself waits up to a second for a frame,
other backends may fail at once."""
AVFOUNDATION = "/System/Library/Frameworks/AVFoundation.framework"


@dataclass(frozen=True, slots=True)
class Reply:
    kind: Literal["ready", "frame", "stalled", "error"]
    image: np.ndarray | None = None
    size: tuple[int, int] = (0, 0)
    """``ready``: the frame size the camera reports, width × height."""
    message: str = ""
    """``ready``: the camera's name, if known; ``error``: why the camera could not be opened."""


def load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise HardwareNotAvailableError("OpenCV is not installed: uv sync") from exc
    return cv2


def camera_names() -> list[str]:
    """Each camera's name, by OpenCV index: on macOS, AVFoundation's video and muxed devices
    sorted by unique ID, as OpenCV sorts them (``orderedVideoCaptureDevices``)."""
    if sys.platform != "darwin":
        raise HardwareNotAvailableError(
            "cameras are found by name on macOS only: empty hardware.camera.name and set "
            "hardware.camera.index"
        )
    try:
        import objc
    except ImportError as exc:
        raise HardwareNotAvailableError("PyObjC is not installed: uv sync") from exc
    objc.loadBundle("AVFoundation", {}, bundle_path=AVFOUNDATION)
    device = objc.lookUpClass("AVCaptureDevice")
    devices: list[Any] = [
        *device.devicesWithMediaType_("vide"),
        *device.devicesWithMediaType_("muxx"),
    ]
    devices.sort(key=functools.cmp_to_key(_by_unique_id))
    return [str(d.localizedName()) for d in devices]


def _by_unique_id(a: Any, b: Any) -> int:
    return int(a.uniqueID().compare_(b.uniqueID()))


def find(index: int, name: str) -> tuple[int, str]:
    """The index to open and that camera's name: the first camera whose name contains ``name``
    (ignoring case), or with no ``name`` the one at ``index`` (its name empty if unknown)."""
    if not name:
        try:
            names = camera_names()
        except HardwareNotAvailableError:
            names = []
        return index, names[index] if index < len(names) else ""
    names = camera_names()
    for found, full in enumerate(names):
        if name.casefold() in full.casefold():
            return found, full
    raise HardwareNotAvailableError(
        f"no camera named like {name!r} is connected (found: {', '.join(names) or 'none'}): "
        "check its USB cable and hub"
    )


def encode(reply: Reply) -> bytes:
    image = reply.image
    header = json.dumps(
        {
            "kind": reply.kind,
            "size": list(reply.size),
            "message": reply.message,
            "shape": list(image.shape) if image is not None else None,
        }
    ).encode()
    payload = image.tobytes() if image is not None else b""
    return PREFIX.pack(len(header), len(payload)) + header + payload


async def receive(stream: asyncio.StreamReader) -> Reply | None:
    """The next reply, or ``None`` once the helper has ended."""
    try:
        header_size, payload_size = PREFIX.unpack(await stream.readexactly(PREFIX.size))
        fields = json.loads(await stream.readexactly(header_size))
        payload = await stream.readexactly(payload_size)
    except asyncio.IncompleteReadError:
        return None
    shape = fields["shape"]
    image = None if shape is None else np.frombuffer(payload, np.uint8).reshape(shape).copy()
    width, height = fields["size"]
    return Reply(fields["kind"], image, (width, height), fields["message"])


def serve(
    index: int,
    width: int,
    height: int,
    warmup: int,
    stall: float,
    requests: BinaryIO,
    replies: BinaryIO,
    name: str = "",
) -> None:
    """Open the camera and answer requests until ``requests`` ends, then release the camera.
    ``width`` and ``height`` 0 keep the camera's own frame size; a ``name`` picks the camera
    instead of ``index`` (``find``)."""
    try:
        index, full_name = find(index, name)
        capture, size = _open(index, width, height, warmup)
    except HardwareNotAvailableError as exc:
        _send(replies, Reply("error", message=str(exc)))
        return
    try:
        _send(replies, Reply("ready", size=size, message=full_name))
        while requests.read(1) == GRAB:
            image = _read(capture, stall)
            _send(replies, Reply("stalled") if image is None else Reply("frame", image))
    finally:
        capture.release()


def main() -> None:
    index, width, height, warmup = (int(value) for value in sys.argv[1:5])
    stall = float(sys.argv[5])
    name = sys.argv[6] if len(sys.argv) > 6 else ""
    replies = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())  # what a library prints stays off the pipe
    try:
        serve(index, width, height, warmup, stall, sys.stdin.buffer, replies, name)
    except BrokenPipeError:
        pass  # the robot has gone; the camera is released all the same
    finally:
        with contextlib.suppress(OSError):
            replies.close()


def _send(replies: BinaryIO, reply: Reply) -> None:
    replies.write(encode(reply))
    replies.flush()


def _read(capture: Any, stall: float) -> np.ndarray | None:
    """The next frame, or ``None`` if none arrives within ``stall`` seconds."""
    deadline = time.monotonic() + stall
    while True:
        ok, image = capture.read()
        if ok and image is not None:
            return np.ascontiguousarray(image, dtype=np.uint8)
        if time.monotonic() >= deadline:
            return None
        time.sleep(RETRY_PAUSE)


def _open(index: int, width: int, height: int, warmup: int) -> tuple[Any, tuple[int, int]]:
    cv2 = load_cv2()
    backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
    capture = cv2.VideoCapture(index, backend)
    if not capture.isOpened():
        capture.release()
        raise HardwareNotAvailableError(
            f"camera {index} could not be opened: run `pasr hardware list`, and check that your "
            "terminal has camera permission"
        )
    if width and height:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    for _ in range(warmup):  # the first frames are dark while exposure settles
        capture.read()
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    return capture, size


if __name__ == "__main__":
    main()
