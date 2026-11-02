"""Stand-in devices for the tests. They act on a ``Room`` instead of the robot, and sleep on
the given clock, so a whole reminder flow runs on virtual time."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from pasr.domain.enums import Direction, Pose, Tilt, WatchAnswer
from pasr.domain.media import AudioChunk, Frame
from pasr.hardware.factory import HardwareBundle
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.clock import Clock
from support.clock import with_timeout
from support.room import LogLine, Room, SeenFace


@dataclass(frozen=True, slots=True, eq=False)
class TaggedFrame(Frame):
    """A frame that carries who is in view and where, for the stand-in face plugin."""

    faces: tuple[SeenFace, ...] = ()


TILT_NODS = {Tilt.LEVEL: 0.0, Tilt.UP: 1.0, Tilt.DOWN: -1.0}
"""HEADNOD units from level for each row of the scan: up moves faces down in the image."""


class FakeHead:
    """Turns the simulated head; the fake camera sees whoever is in that direction."""

    def __init__(self, room: Room, clock: Clock) -> None:
        self.room = room
        self.clock = clock
        self.pose_history: list[Pose] = []
        self.nudges: list[tuple[float, float]] = []
        self.views: list[tuple[float, Direction]] = []
        """(nod, direction) of every ``look``, for checking the scan's path."""

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def look(self, direction: Direction, speed: int = 5) -> None:
        turned, nodded = self.room.head_offset
        if direction is not self.room.head_direction or turned:
            await self.clock.sleep(1.0 / max(speed, 1))
        self.room.head_direction = direction
        self.room.head_offset = (0.0, nodded)
        self.views.append((nodded, direction))

    async def tilt(self, tilt: Tilt, speed: int = 5) -> None:
        turned, nodded = self.room.head_offset
        if TILT_NODS[tilt] != nodded:
            await self.clock.sleep(1.0 / max(speed, 1))
        self.room.head_offset = (turned, TILT_NODS[tilt])

    async def nudge(self, turn: float, nod: float, speed: int = 5) -> tuple[float, float]:
        self.nudges.append((turn, nod))
        turned, nodded = self.room.head_offset
        self.room.head_offset = (turned + turn, nodded + nod)
        await self.clock.sleep(1.0 / max(speed, 1))
        return turn, nod

    async def pose(self, pose: Pose) -> None:
        self.pose_history.append(pose)
        self.room.head_offset = (self.room.head_offset[0], 0.0)
        await self.look(Direction.FRONT)

    async def blink(self) -> None:
        pass


SECONDS_PER_WORD = 0.35


class FakeSpeaker:
    """Records what the robot says and takes about as long as speaking it would."""

    def __init__(self, room: Room, clock: Clock) -> None:
        self.room = room
        self.clock = clock

    async def say(self, text: str) -> None:
        self.room.spoken.append(LogLine(self.clock.now(), text))
        self.room.heard(text)
        await self.clock.sleep(SECONDS_PER_WORD * max(len(text.split()), 1))


FRAME_INTERVAL_S = 0.1
FRAME_SIZE = (320, 240)
"""Width and height of the stand-in camera's frames."""


class FakeCamera:
    """Sees the people the simulated room places in the direction the head is facing, where the
    head's turn and nod put them in the image."""

    def __init__(self, room: Room, clock: Clock) -> None:
        self.room = room
        self.clock = clock

    async def open(self) -> None:
        self.room.camera_on = True
        self.room.camera_opened += 1

    async def close(self) -> None:
        self.room.camera_on = False
        self.room.asked_pose = None  # done: people relax

    async def grab(self) -> Frame:
        if not self.room.camera_on:
            raise RuntimeError("camera is not open")
        await self.clock.sleep(FRAME_INTERVAL_S)
        self.room.camera_grabs += 1
        width, height = FRAME_SIZE
        return TaggedFrame(
            image=np.zeros((height, width, 3), dtype=np.uint8),
            captured_at=self.clock.now(),
            faces=self.room.in_view(width, height),
        )


SPEECH_RMS = 0.15
ROOM_NOISE_RMS = 0.002


class FakeMicrophone:
    """Synthesises audio from the simulated room: loud noise while someone speaks, quiet room
    noise otherwise. Real VAD plugins (e.g. ``energy``) therefore work on it unchanged."""

    def __init__(self, room: Room, clock: Clock, *, sample_rate: int, chunk_ms: int) -> None:
        self.room = room
        self.clock = clock
        self.sample_rate = sample_rate
        self.chunk = timedelta(milliseconds=chunk_ms)
        self._rng = np.random.default_rng()

    async def stream(self) -> AsyncGenerator[AudioChunk, None]:
        self.room.microphone_opened += 1
        n = int(self.sample_rate * self.chunk.total_seconds())
        start = self.clock.now()
        while True:
            await self.clock.sleep_until(start + self.chunk)  # a chunk is ready once recorded
            voice = self.room.voice_at(start)
            level = SPEECH_RMS if voice else ROOM_NOISE_RMS
            yield AudioChunk(
                samples=(self._rng.standard_normal(n) * level).astype(np.float32),
                sample_rate=self.sample_rate,
                start=start,
            )
            start += self.chunk


class FakeWatch:
    """A watch answered by the test's scripted answers; an unscripted prompt times out. Like
    ``BangleWatch`` it reconnects before each request, which fails while the owner is away."""

    def __init__(self, room: Room, clock: Clock) -> None:
        self.room = room
        self.clock = clock
        self._connected = False
        self.app_missing = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.room.watch_in_range()

    async def connect(self) -> None:
        if not self.room.watch_in_range():
            self._connected = False
            raise HardwareNotAvailableError("no Bluetooth device named Bangle.js* found")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def _link(self) -> None:
        if not self.is_connected:
            await self.connect()

    async def ping(self) -> bool:
        await self._link()
        return not self.app_missing

    async def prompt(self, text: str, timeout_s: float) -> WatchAnswer:
        await self._link()
        prompt = self.room.open_prompt(text, timeout_s)
        responder: asyncio.Task[None] | None = None
        if self.room.scripted_answers:
            scripted = self.room.scripted_answers.popleft()
            responder = asyncio.ensure_future(
                self._answer_later(prompt.id, scripted.answer, scripted.delay_s)
            )
        try:
            answer = await with_timeout(self.clock, asyncio.shield(prompt.future), timeout_s)
            return answer or WatchAnswer.TIMEOUT
        finally:
            self.room.close_prompt(prompt)
            if responder is not None:
                responder.cancel()

    async def _answer_later(self, prompt_id: int, answer: WatchAnswer, delay_s: float) -> None:
        if answer is WatchAnswer.TIMEOUT:
            return
        await self.clock.sleep(delay_s)
        self.room.answer(prompt_id, answer)

    async def notify(self, text: str) -> None:
        await self._link()
        self.room.watch_notifications.append(LogLine(self.clock.now(), text))


@dataclass(slots=True)
class StandInHardware(HardwareBundle):
    room: Room


def stand_in_hardware(
    room: Room, clock: Clock, *, sample_rate: int = 16000, chunk_ms: int = 250
) -> StandInHardware:
    return StandInHardware(
        FakeHead(room, clock),
        FakeSpeaker(room, clock),
        FakeCamera(room, clock),
        FakeMicrophone(room, clock, sample_rate=sample_rate, chunk_ms=chunk_ms),
        FakeWatch(room, clock),
        room,
    )
