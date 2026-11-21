"""Time sources. Everything time-related in the robot goes through a ``Clock``, so the reminder
flow can be driven on virtual time in tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep_until(self, when: datetime) -> None: ...

    async def sleep(self, seconds: float) -> None: ...


def local_now() -> datetime:
    return datetime.now().astimezone()


class SystemClock:
    """Wall-clock time in the local time zone."""

    def now(self) -> datetime:
        return local_now()

    async def sleep_until(self, when: datetime) -> None:
        remaining = (when - self.now()).total_seconds()
        await asyncio.sleep(max(remaining, 0.0))

    async def sleep(self, seconds: float) -> None:
        await self.sleep_until(self.now() + timedelta(seconds=seconds))


async def first_of(*awaitables: Awaitable[object]) -> int:
    """Wait for the first awaitable to finish, cancel the rest, return the winner's index."""
    tasks = [asyncio.ensure_future(a) for a in awaitables]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        winner = next(t for t in tasks if t in done)
        winner.result()  # re-raise its exception, if any
        return tasks.index(winner)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
