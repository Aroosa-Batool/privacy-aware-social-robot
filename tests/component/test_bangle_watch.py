"""BangleWatch against an emulation of bangle/consent_app.js on the Espruino console."""

import asyncio
from collections.abc import Callable

import pytest

from fakes import ConsentAppConsole
from pasr.domain.enums import WatchAnswer
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.watch.bangle import BangleWatch


class EmulatedBangle:
    """A transport whose far end is the consent app's console."""

    def __init__(self, console: ConsentAppConsole | None = None) -> None:
        self.console = console or ConsentAppConsole()
        self.connected = False
        self.connects = 0
        self._buffer = b""
        self._on_data: Callable[[bytes], None] | None = None

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self, on_data: Callable[[bytes], None]) -> None:
        self.connected, self._on_data = True, on_data
        self.connects += 1

    async def disconnect(self) -> None:
        self.connected = False

    async def write(self, data: bytes) -> None:
        assert len(data) <= 20, "writes must fit the Bangle.js 1 MTU"
        self._buffer += data
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            asyncio.get_running_loop().call_soon(self._print, self.console.evaluate(line))

    def _print(self, output: list[str]) -> None:
        assert self._on_data is not None
        data = "".join(f"{line}\r\n" for line in output).encode()
        for i in range(0, len(data), 7):  # notifications arrive fragmented
            self._on_data(data[i : i + 7])


async def test_prompt_answers_and_passes_the_timeout():
    for answer, expected in [("YES", WatchAnswer.YES), ("NO", WatchAnswer.NO)]:
        transport = EmulatedBangle(ConsentAppConsole(answer))
        watch = BangleWatch(transport)
        assert await watch.prompt("Someone is here. Say it out loud?", 30) is expected
        assert transport.console.received == [("consent", "Someone is here. Say it out loud?", 30)]


async def test_unanswered_prompt_times_out():
    watch = BangleWatch(EmulatedBangle(ConsentAppConsole(answer=None)), reply_margin_s=0.01)
    assert await watch.prompt("?", 0.01) is WatchAnswer.TIMEOUT


async def test_notify_ping_and_reconnect():
    transport = EmulatedBangle()
    watch = BangleWatch(transport)
    await watch.notify("Reminder: Doctor’s “check”")
    await transport.disconnect()
    assert await watch.ping()
    assert transport.connects == 2  # reconnected before the request
    assert transport.console.received == [("notify", "Reminder: Doctor’s “check”"), ("ping",)]


async def test_a_watch_without_the_app_is_reported():
    watch = BangleWatch(EmulatedBangle(ConsentAppConsole(loaded=False)), reply_margin_s=0.05)
    assert not await watch.ping() and watch.app_missing
    with pytest.raises(HardwareNotAvailableError, match="consent_app.js loaded"):
        await watch.notify("Reminder: Dentist")
    assert await watch.prompt("?", 0.01) is WatchAnswer.TIMEOUT
