from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from pasr.orchestration.clock import Clock, first_of

logger = logging.getLogger(__name__)

Tick = Callable[[], Awaitable[datetime | None]]


class PollingScheduler:
    """Calls ``tick`` repeatedly. ``tick`` does due work and returns when it next wants to run;
    the scheduler also re-polls at least every ``poll_interval`` (to pick up database changes
    made by other processes) and immediately when ``poke`` is called."""

    def __init__(self, clock: Clock, tick: Tick, poll_interval: Callable[[], float]) -> None:
        self.clock = clock
        self._tick = tick
        self._poll_interval = poll_interval
        self._poke = asyncio.Event()

    def poke(self) -> None:
        self._poke.set()

    async def run(self) -> None:
        while True:
            self._poke.clear()
            try:
                next_at = await self._tick()
            except Exception:
                logger.exception("checking for due reminders failed")
                next_at = None
            limit = self.clock.now() + timedelta(seconds=self._poll_interval())
            wake = min(next_at, limit) if next_at is not None else limit
            if not self._poke.is_set():
                await first_of(self.clock.sleep_until(wake), self._poke.wait())
