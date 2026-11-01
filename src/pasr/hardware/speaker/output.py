"""Play the robot's voice on a chosen output device instead of the macOS default.

macOS ``say`` and ``afplay`` always use the system default output, which AirPods or a display
can take over. ``sounddevice`` can address any output device by name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pasr.hardware.protocols import HardwareNotAvailableError


def _audio_libraries() -> tuple[Any, Any]:
    try:
        import sounddevice
        import soundfile
    except ImportError as exc:
        raise HardwareNotAvailableError(
            "playing on hardware.speaker.output_device needs sounddevice: uv sync"
        ) from exc
    return sounddevice, soundfile


def find_output_device(name: str) -> int:
    """Index of the output device called ``name`` (or starting with it, like ``say -a``)."""
    sounddevice, _ = _audio_libraries()
    outputs = [
        (index, str(device["name"]))
        for index, device in enumerate(sounddevice.query_devices())
        if int(device["max_output_channels"]) > 0
    ]
    exact = [index for index, device_name in outputs if device_name == name]
    prefix = [index for index, device_name in outputs if device_name.startswith(name)]
    if exact or prefix:
        return (exact or prefix)[0]
    known = ", ".join(repr(n) for _, n in outputs) or "none"
    raise HardwareNotAvailableError(
        f"audio output {name!r} not found (outputs: {known}); set hardware.speaker.output_device"
    )


def device_player(name: str) -> Callable[..., None]:
    """A ``playsound``-compatible function that plays a sound file on output ``name``,
    blocking until done. The device is looked up now, so a wrong name fails early."""
    sounddevice, soundfile = _audio_libraries()
    index = find_output_device(name)

    def play(path: str, *args: Any, **kwargs: Any) -> None:
        data, rate = soundfile.read(str(path), dtype="float32")
        sounddevice.play(data, rate, device=index, blocking=True)

    return play
