"""Virtual time for tests: the 7-minute reminder flow runs in milliseconds."""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import Awaitable
from contextlib import suppress
from datetime import datetime, timedelta

from pasr.orchestration.clock import Clock, first_of, local_now


class VirtualClockStalledError(RuntimeError):
    pass


class VirtualClock:
    """Simulated time that jumps straight to the next timer whenever every task is waiting.

    Only code that sleeps through this clock is accelerated, so simulations must not block on
    real-time ``asyncio.sleep``. Work in a thread (``asyncio.to_thread``, as devices do) is
    waited for in real time, up to ``stall_grace_seconds``, before the clock calls it a stall.
    """

    def __init__(
        self,
        start: datetime | None = None,
        *,
        settle_iterations: int = 30,
        stall_grace_seconds: float = 1.0,
    ) -> None:
        self._now = start or local_now().replace(microsecond=0)
        self._timers: list[tuple[datetime, int, asyncio.Future[None]]] = []
        self._sequence = itertools.count()
        self._settle_iterations = settle_iterations
        self._stall_grace_seconds = stall_grace_seconds

    def now(self) -> datetime:
        return self._now

    async def sleep_until(self, when: datetime) -> None:
        if when <= self._now:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._timers, (when, next(self._sequence), future))
        await future

    async def sleep(self, seconds: float) -> None:
        await self.sleep_until(self._now + timedelta(seconds=seconds))

    def _fire_next(self) -> bool:
        while self._timers:
            when, _, future = heapq.heappop(self._timers)
            if future.done():  # cancelled sleeper
                continue
            self._now = max(self._now, when)
            future.set_result(None)
            return True
        return False

    async def _settle(self) -> None:
        for _ in range(self._settle_iterations):
            await asyncio.sleep(0)

    async def _wait_for_threads(self, task: asyncio.Future[object]) -> bool:
        """No timer is pending: give work in threads real time to hand its result back (a slow
        CI machine needs more than the settle iterations). True once the simulation moves on."""
        waited, pause = 0.0, 0.001
        while waited < self._stall_grace_seconds:
            await asyncio.sleep(pause)
            waited += pause
            pause = min(pause * 2, 0.05)
            await self._settle()
            if task.done() or self._fire_next():
                return True
        return False

    async def drive[T](self, awaitable: Awaitable[T], *, max_seconds: float = 7 * 86400) -> T:
        """Run ``awaitable`` to completion, advancing virtual time whenever the system is idle."""
        task = asyncio.ensure_future(awaitable)
        deadline = self._now + timedelta(seconds=max_seconds)
        try:
            while True:
                await self._settle()
                if task.done():
                    return task.result()
                if self._now > deadline:
                    raise TimeoutError(f"simulation exceeded {max_seconds} virtual seconds")
                if not self._fire_next() and not await self._wait_for_threads(task):
                    raise VirtualClockStalledError(
                        "no pending timers and the simulation has not finished"
                    )
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task


async def with_timeout[T](clock: Clock, awaitable: Awaitable[T], seconds: float) -> T | None:
    """Await with a timeout measured on ``clock``; ``None`` on timeout."""
    task = asyncio.ensure_future(awaitable)
    if await first_of(task, clock.sleep(seconds)) == 0:
        return task.result()
    return None
