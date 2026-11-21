"""Real cameras: the head-mounted USB webcam through OpenCV, and a researcher-supplied folder of
images for offline experiments.

Frames stay in memory; writing images is blocked by a lint rule (docs/PRIVACY.md). The device is
opened only in ``open`` and released in ``close`` so the camera (and its LED) is off whenever the
robot is not enrolling or scanning. The webcam is opened in a helper process (``helper``), so a
camera that drops off USB for a moment can be reconnected (ADR 0010).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pasr.domain.media import Frame
from pasr.hardware.camera import helper
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.clock import Clock
from pasr.paths import resolve

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp")
STALL_SECONDS = 3.0
"""How long a camera may send no frame before it is reconnected. A USB camera behind a hub can
pause its stream for a moment, e.g. while the head turns."""
RECONNECT_SECONDS = 10.0
"""How long a camera that sent no frame is reconnected for before it counts as failed. One that
dropped off USB is usually back within a second."""
RECONNECT_PAUSE = 0.5
OPEN_SECONDS = 15.0
"""How long a helper may take to start and open its camera, besides a second per warm-up frame."""
REPLY_MARGIN = 5.0
"""How much longer than the stall a frame may take to arrive before the helper counts as hung."""
STOP_SECONDS = 5.0


class CameraHelper:
    """A helper process with one camera open in it (see ``helper``)."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        size: tuple[int, int],
        stall: float,
        name: str = "",
    ) -> None:
        self._process = process
        self.size = size
        """Width × height of the camera's frames."""
        self._stall = stall
        self.name = name
        """The camera's name; empty if unknown."""

    @classmethod
    async def start(
        cls,
        index: int,
        width: int,
        height: int,
        *,
        warmup: int,
        stall: float = STALL_SECONDS,
        name: str = "",
        command: Sequence[str] | None = None,
    ) -> CameraHelper:
        """``width`` and ``height`` 0 keep the camera's own frame size; a ``name`` opens the
        first camera whose name contains it instead of the one at ``index``."""
        process = await asyncio.create_subprocess_exec(
            *(command or helper.COMMAND),
            *(str(value) for value in (index, width, height, warmup, stall, name)),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            start_new_session=True,  # Ctrl+C stops the robot, which then closes the camera
        )
        assert process.stdout is not None
        limit = OPEN_SECONDS + warmup
        try:
            reply = await asyncio.wait_for(helper.receive(process.stdout), limit)
        except TimeoutError:
            _kill(process)
            raise HardwareNotAvailableError(
                f"camera {name or index} did not open within {limit:.0f} s"
            ) from None
        except BaseException:  # cancelled: never leave a camera on
            _kill(process)
            raise
        if reply is None or reply.kind != "ready":
            await _end(process)
            raise HardwareNotAvailableError(
                reply.message if reply is not None else f"camera {name or index}: its helper ended"
            )
        return cls(process, reply.size, stall, reply.message)

    async def grab(self) -> np.ndarray | None:
        """The next frame; ``None`` if none came: the stream stalled, or the helper ended or
        hung."""
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None and stdout is not None
        try:
            stdin.write(helper.GRAB)
            await stdin.drain()
            reply = await asyncio.wait_for(helper.receive(stdout), self._stall + REPLY_MARGIN)
        except (OSError, TimeoutError):  # the pipe broke: the helper has ended
            return None
        return reply.image if reply is not None and reply.kind == "frame" else None

    async def stop(self) -> None:
        """Close the pipe: the helper releases the camera and ends (killed if it hangs)."""
        await _end(self._process)


async def _end(process: asyncio.subprocess.Process) -> None:
    try:  # closes stdin and takes what is still coming, so the helper is never stuck writing
        await asyncio.wait_for(process.communicate(), STOP_SECONDS)
    except TimeoutError:
        _kill(process)
        await process.wait()
    except asyncio.CancelledError:
        _kill(process)
        raise


def _kill(process: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        process.kill()


class OpenCVCamera:
    """The webcam, in a helper process. When it sends no frame, e.g. because it dropped off USB
    for a moment, fresh helpers reconnect it. With a ``name``, each helper finds the camera by
    name; ``index`` is used only without one."""

    def __init__(
        self,
        index: int,
        width: int,
        height: int,
        *,
        clock: Clock,
        name: str | None = None,
        warmup_frames: int = 5,
        stall_seconds: float = STALL_SECONDS,
        reconnect_seconds: float = RECONNECT_SECONDS,
        command: Sequence[str] | None = None,
    ) -> None:
        self.index = index
        self.name = name
        self.label = f"camera {name!r}" if name else f"camera {index}"
        """How messages name the camera."""
        self.width = width
        self.height = height
        self.clock = clock
        self.warmup_frames = warmup_frames
        self.stall_seconds = stall_seconds
        self.reconnect_seconds = reconnect_seconds
        self.command = command
        self._helper: CameraHelper | None = None
        self._delivered = False
        """A frame came since ``open``: if frames then stop, the camera dropped off."""

    async def open(self) -> None:
        if self._helper is None:
            self._delivered = False
            self._helper = await self._start()

    async def close(self) -> None:
        camera, self._helper = self._helper, None
        if camera is not None:
            await camera.stop()

    async def grab(self) -> Frame:
        if self._helper is None:
            raise RuntimeError("camera is not open")
        image = await self._helper.grab()
        if image is None:
            image = await self._reconnect()
        self._delivered = True
        return Frame(image=image, captured_at=self.clock.now())

    async def _start(self) -> CameraHelper:
        return await CameraHelper.start(
            self.index,
            self.width,
            self.height,
            warmup=self.warmup_frames,
            stall=self.stall_seconds,
            name=self.name or "",
            command=self.command,
        )

    async def _reconnect(self) -> np.ndarray:
        """No frame came: start fresh helpers, which also find a camera that dropped off USB and
        came back, until one sends a frame or ``reconnect_seconds`` pass."""
        logger.warning(
            "%s sent no frame for %.0f s: reconnecting it", self.label, self.stall_seconds
        )
        deadline = time.monotonic() + self.reconnect_seconds
        while True:
            await self.close()
            try:
                camera = self._helper = await self._start()
                image = await camera.grab()
                problem = f"no frame for {self.stall_seconds:.0f} s"
            except HardwareNotAvailableError as exc:
                image, problem = None, str(exc)
            if image is not None:
                logger.info("%s is back", self.label, extra={"toast": True})
                return image
            if time.monotonic() >= deadline:
                raise HardwareNotAvailableError(self._lost(problem))
            await asyncio.sleep(RECONNECT_PAUSE)

    def _lost(self, problem: str) -> str:
        if self._delivered:
            return (
                f"{self.label} stopped sending frames and did not come back within "
                f"{self.reconnect_seconds:.0f} s ({problem}). Check its USB cable and hub: it "
                "may lose its connection as the head turns"
            )
        which = (
            ""
            if self.name
            else "Is it the head camera? Find it under Settings › Setup (an iPhone or the "
            "laptop's own camera may have another index); "
        )
        return (
            f"{self.label} sent no frame, even after reconnecting for "
            f"{self.reconnect_seconds:.0f} s ({problem}). {which}"
            "check its USB cable and hub, and close other apps that use it"
        )


class ImageFolderCamera:
    """Images read in name order; ``grab`` cycles through them. Read-only (ADR 0002): the robot
    never writes images, and these are the researcher's own files."""

    def __init__(self, folder: Path, *, clock: Clock) -> None:
        self.folder = resolve(folder)
        self.clock = clock
        self._files: list[Path] = []
        self._next = 0
        self._open = False

    async def open(self) -> None:
        files = (
            sorted(p for p in self.folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            if self.folder.is_dir()
            else []
        )
        if not files:
            raise HardwareNotAvailableError(
                f"no images ({', '.join(IMAGE_SUFFIXES)}) in {self.folder}"
            )
        self._files = files
        self._open = True

    async def close(self) -> None:
        self._open = False

    async def grab(self) -> Frame:
        if not self._open:
            raise RuntimeError("camera is not open")
        path = self._files[self._next % len(self._files)]
        self._next += 1
        image = await asyncio.to_thread(self._read, path)
        return Frame(image=image, captured_at=self.clock.now())

    def _read(self, path: Path) -> Any:
        image = helper.load_cv2().imread(str(path))
        if image is None:
            raise HardwareNotAvailableError(f"could not read image {path}")
        return np.ascontiguousarray(image, dtype=np.uint8)
