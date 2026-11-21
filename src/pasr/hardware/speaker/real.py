from __future__ import annotations

import asyncio

from pasr.hardware.ohbot_driver import OhbotDriver
from pasr.hardware.protocols import HardwareNotAvailableError


class OhbotSpeaker:
    """Text-to-speech through ``ohbot.say`` with lip sync. Starts the shared driver itself, so it
    can speak before the head has connected. ``output_device`` plays the voice on that
    device instead of the macOS default output."""

    def __init__(
        self, port: str, *, output_device: str | None = None, driver: OhbotDriver | None = None
    ) -> None:
        self.driver = driver or OhbotDriver.shared(port)
        self.output_device = output_device

    async def say(self, text: str) -> None:
        await asyncio.to_thread(self.driver.ensure_started)
        await asyncio.to_thread(self.driver.say, text, output_device=self.output_device)


class MacSaySpeaker:
    """Plain macOS ``say`` without head movement. Runs as a subprocess with argv, no shell, and
    writes no file. ``output_device`` is passed to ``say -a`` (a name or name prefix)."""

    def __init__(self, voice: str | None = None, output_device: str | None = None) -> None:
        self.voice = voice
        self.output_device = output_device

    async def say(self, text: str) -> None:
        args = ["say", *(["-v", self.voice] if self.voice else [])]
        args += ["-a", self.output_device] if self.output_device else []
        try:
            process = await asyncio.create_subprocess_exec(
                *args, text if text[:1] != "-" else f" {text}"
            )
        except FileNotFoundError as exc:
            raise HardwareNotAvailableError("macOS 'say' is not available on this system") from exc
        if await process.wait() != 0:
            raise HardwareNotAvailableError(f"'say' exited with status {process.returncode}")
