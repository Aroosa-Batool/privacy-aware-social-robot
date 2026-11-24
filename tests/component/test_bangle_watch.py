"""BangleWatch against an emulation of bangle/consent_app.js on the Espruino console."""

import asyncio
from collections.abc import Callable
from datetime import timedelta

import pytest

from conftest import stand_ins
from fakes import ConsentAppConsole
from pasr.domain.enums import DeliveryChannel, Direction, ReminderOrigin, WatchAnswer
from pasr.hardware.protocols import HardwareNotAvailableError, WatchPromptDisplayError
from pasr.hardware.watch.bangle import BangleWatch
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime


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
    with pytest.raises(WatchPromptDisplayError):
        await watch.prompt("?", 0.01)
    assert watch.app_missing


@pytest.mark.parametrize("legacy", [False, True])
async def test_display_errors_and_legacy_apps_never_supply_an_answer(legacy):
    console = ConsentAppConsole("NO" if legacy else "DISPLAY_ERROR", legacy=legacy)
    watch = BangleWatch(EmulatedBangle(console))
    assert await watch.ping()
    with pytest.raises(WatchPromptDisplayError):
        await watch.prompt("?", 30)
    await watch.notify("Private reminder")
    assert console.received[-1] == ("notify", "Private reminder")
    if legacy:
        assert all(command[0] != "consent" for command in console.received)


async def test_late_and_duplicate_replies_cannot_answer_the_next_prompt():
    transport = EmulatedBangle(ConsentAppConsole(answer=None))
    watch = BangleWatch(transport, reply_margin_s=0.01)
    assert await watch.prompt("First?", 0.01) is WatchAnswer.TIMEOUT
    second = asyncio.create_task(watch.prompt("Second?", 5))
    await asyncio.sleep(0)  # the second request is waiting for its own ID
    transport._print(["CONSENT:1:YES", "CONSENT:1:DISPLAY_ERROR"])
    await asyncio.sleep(0)
    assert not second.done()
    transport._print(["CONSENT:2:NO", "CONSENT:2:YES"])
    assert await second is WatchAnswer.NO


async def test_tied_reminders_store_only_the_explicit_answer(make_settings, clock):
    class TwoPrompts(ConsentAppConsole):
        first_id = None

        def evaluate(self, line):
            match = self.CONSENT.match(line[1:].decode("ascii"))
            if not match:
                return super().evaluate(line)
            request_id = match[1]
            if self.first_id is None:
                self.first_id = request_id
                return [f"CONSENT:{request_id}:DISPLAY_ERROR"]
            return [
                f"CONSENT:{self.first_id}:YES",
                f"CONSENT:{request_id}:NO",
                f"CONSENT:{request_id}:YES",
            ]

    settings = make_settings(
        privacy={"detection_modality": "camera_only", "disclosure_policy": "ask_once_per_bystander"}
    )
    hardware = stand_ins(settings, clock)
    hardware.watch = BangleWatch(EmulatedBangle(TwoPrompts()))
    runtime = Runtime(settings, clock=clock, hardware=hardware, inline_compute=True)

    async def run():
        await runtime.start()
        try:
            runtime.enrollment.register("Owner")
            await runtime.enrollment.enroll_face()
            hardware.room.set_faces(Direction.RIGHT, ["visitor"])
            due = clock.now() + timedelta(minutes=3)
            reminders = [
                runtime.service.create(title, due, origin=ReminderOrigin.CLI, sensitive=True)
                for title in ("First", "Second")
            ]
            first, second = await asyncio.gather(
                *(runtime.reminders.wait_for(reminder.id) for reminder in reminders)
            )
            assert first.channel is second.channel is DeliveryChannel.WATCH
            assert first.error == "WatchPromptDisplayError" and second.error is None
            starts = [e.reminder_id for e in runtime.bus.recent if e.type is EventType.FLOW_STARTED]
            assert starts == [first.reminder_id, second.reminder_id]
            answers = [e for e in runtime.bus.recent if e.type is EventType.CONSENT_ANSWERED]
            assert [(e.reminder_id, e.data["answer"]) for e in answers] == [
                (second.reminder_id, "no")
            ]
            records = runtime.repos.consents.all()
            assert [(r.reminder_id, r.allowed) for r in records] == [(second.reminder_id, False)]
            assert len(runtime.repos.bystanders.all()) == 1
            assert not any("reminder:" in s.text.lower() for s in hardware.room.spoken)
        finally:
            await runtime.stop()

    await clock.drive(run())
