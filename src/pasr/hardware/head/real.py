from __future__ import annotations

import asyncio

from pasr.domain.enums import Direction, Pose, Tilt
from pasr.hardware.ohbot_driver import (
    HEADNOD,
    HEADTURN,
    LIDBLINK,
    POSES,
    NodPositions,
    OhbotDriver,
    TurnPositions,
)

BLINK_SECONDS = 0.15
FULL_TURN = 10.0
"""The motors' range is 0 to ``FULL_TURN``."""


def _within_range(position: float) -> float:
    return min(max(position, 0.0), FULL_TURN)


class OhbotHead:
    """Ohbot motors over USB serial through the shared ``OhbotDriver``.

    ``look`` and ``nudge`` return when the motors should have arrived (a speed-scaled estimate ,
    the library gives no feedback); the scan step then waits ``scan.settle_seconds`` before
    grabbing frames. Before the first ``pose``, ``nudge`` takes the nod to be the attention pose's.
    """

    def __init__(
        self,
        port: str,
        *,
        turns: TurnPositions,
        nods: NodPositions,
        move_seconds: float,
        driver: OhbotDriver | None = None,
    ) -> None:
        self.driver = driver or OhbotDriver.shared(port)
        self.turns = turns
        self.nods = nods
        self.move_seconds = move_seconds
        self._position: float | None = None
        self._nod: float | None = None

    async def connect(self) -> None:
        await asyncio.to_thread(self.driver.ensure_started)
        await self.look(Direction.FRONT)

    async def close(self) -> None:
        if not self.driver.started:
            return
        try:
            await self.pose(Pose.REST)
        finally:
            await asyncio.to_thread(self.driver.stop)

    async def look(self, direction: Direction, speed: int = 5) -> None:
        target = self.turns.for_direction(direction)
        await asyncio.to_thread(self.driver.move, HEADTURN, target, speed)
        delta = FULL_TURN if self._position is None else abs(target - self._position)
        self._position = target
        await self._arrive(delta, speed)

    async def tilt(self, tilt: Tilt, speed: int = 5) -> None:
        target = self.nods.for_tilt(tilt)
        start = POSES[Pose.ATTENTION][HEADNOD] if self._nod is None else self._nod
        if target != start:
            await asyncio.to_thread(self.driver.move, HEADNOD, target, speed)
            self._nod = target
            await self._arrive(abs(target - start), speed)

    async def nudge(self, turn: float, nod: float, speed: int = 5) -> tuple[float, float]:
        start_turn = self.turns.front if self._position is None else self._position
        start_nod = POSES[Pose.ATTENTION][HEADNOD] if self._nod is None else self._nod
        end_turn, end_nod = _within_range(start_turn + turn), _within_range(start_nod + nod)
        if end_turn != start_turn:
            await asyncio.to_thread(self.driver.move, HEADTURN, end_turn, speed)
            self._position = end_turn
        if end_nod != start_nod:
            await asyncio.to_thread(self.driver.move, HEADNOD, end_nod, speed)
            self._nod = end_nod
        turned, nodded = end_turn - start_turn, end_nod - start_nod
        await self._arrive(max(abs(turned), abs(nodded)), speed)
        return turned, nodded

    async def pose(self, pose: Pose) -> None:
        for motor, position in POSES[pose].items():
            await asyncio.to_thread(self.driver.move, motor, position, 5)
        self._nod = POSES[pose].get(HEADNOD, self._nod)
        await self.look(Direction.FRONT)

    async def _arrive(self, distance: float, speed: int) -> None:
        """Wait while the motors move ``distance`` units (both motors move at once)."""
        await asyncio.sleep(self.move_seconds * (distance / FULL_TURN) * (5 / max(speed, 1)))

    async def blink(self) -> None:
        await asyncio.to_thread(self.driver.move, LIDBLINK, 0, 10)
        await asyncio.sleep(BLINK_SECONDS)
        await asyncio.to_thread(self.driver.move, LIDBLINK, 10, 10)
