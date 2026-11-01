from __future__ import annotations

from typing import Protocol


class App(Protocol):
    """A feature of the personal robot (reminders today; more later).

    The runtime builds apps with the shared ``RobotContext``, starts them after the hardware is
    connected and stops them before it is released.
    """

    name: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...
