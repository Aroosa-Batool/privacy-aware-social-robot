"""Connect to each real device once and report. Used by ``pasr hardware check``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass

import numpy as np

from pasr.domain.enums import Direction
from pasr.hardware.discovery import default_audio_output
from pasr.hardware.factory import HardwareBundle, build_hardware
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.clock import SystemClock
from pasr.paths import resolve
from pasr.settings.loader import update_overrides
from pasr.settings.schema import DEVICES, Device, Settings

CHECK_PHRASE = "Robot check."
MICROPHONE_CHUNKS = 5


@dataclass(frozen=True, slots=True)
class DeviceReport:
    device: Device
    ok: bool
    detail: str


async def _check_head(hw: HardwareBundle, settings: Settings) -> str:
    await hw.head.connect()
    try:
        await hw.head.blink()
        for direction in (Direction.LEFT, Direction.FRONT, Direction.RIGHT):
            await hw.head.look(direction, settings.scan.head_speed)
    finally:
        await hw.head.close()
    return "blinked and looked left, front, right"


async def _check_speaker(hw: HardwareBundle, settings: Settings) -> str:
    await hw.speaker.say(CHECK_PHRASE)
    if device := settings.hardware.speaker.output_device:
        return f"said {CHECK_PHRASE!r} through {device!r} (hardware.speaker.output_device)"
    output = await asyncio.to_thread(default_audio_output)
    where = f" through {output!r} (the macOS default output)" if output else ""
    return f"said {CHECK_PHRASE!r}{where}"


async def _check_camera(hw: HardwareBundle, settings: Settings) -> str:
    await hw.camera.open()
    try:
        frame = await hw.camera.grab()
    finally:
        await hw.camera.close()
    height, width = frame.image.shape[:2]
    return f"frame {width}x{height}"


async def _check_microphone(hw: HardwareBundle, settings: Settings) -> str:
    chunks = []
    async with aclosing(hw.microphone.stream()) as stream:
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) >= MICROPHONE_CHUNKS:
                break
    if not chunks:
        raise HardwareNotAvailableError("the microphone produced no audio")
    samples = np.concatenate([c.samples for c in chunks])
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) if samples.size else 0.0
    return f"{chunks[0].sample_rate} Hz, {len(chunks)} chunks, RMS {rms:.4f}"


async def _check_watch(hw: HardwareBundle, settings: Settings) -> str:
    await hw.watch.connect()
    try:
        if not await hw.watch.ping():
            if hw.watch.app_missing:
                raise HardwareNotAvailableError(
                    "connected, but the consent app is not loaded on the watch (consent is "
                    "not defined): send bangle/consent_app.js from the Espruino IDE "
                    "(bangle/README.md)"
                )
            raise HardwareNotAvailableError("connected, but the watch's console did not answer")
    finally:
        await hw.watch.disconnect()
    return f"connected and answered (address {settings.hardware.watch.address or 'not cached'})"


CHECKS: dict[Device, Callable[[HardwareBundle, Settings], Awaitable[str]]] = {
    "ohbot": _check_head,
    "speaker": _check_speaker,
    "camera": _check_camera,
    "microphone": _check_microphone,
    "watch": _check_watch,
}


async def check_devices(
    settings: Settings,
    *,
    only: Sequence[Device] | None = None,
    hardware: HardwareBundle | None = None,
) -> list[DeviceReport]:
    """Exercise each selected device in turn. Failures become reports, never exceptions. The
    caller should hold the ``RuntimeLock``: a running robot owns the devices."""
    devices = tuple(only) if only else DEVICES
    data_dir = resolve(settings.storage.data_dir)

    def remember_watch(address: str) -> None:
        update_overrides(data_dir, {"hardware": {"watch": {"address": address}}})

    hw = hardware or build_hardware(
        settings.hardware, clock=SystemClock(), on_watch_address=remember_watch
    )
    reports: list[DeviceReport] = []
    for device in devices:
        try:
            detail = await CHECKS[device](hw, settings)
        except Exception as exc:  # report and continue with the next device
            reports.append(DeviceReport(device, False, f"{type(exc).__name__}: {exc}"))
        else:
            reports.append(DeviceReport(device, True, detail))
    return reports
