"""Find candidate devices for the settings. Used by ``pasr hardware list``; each probe is
skipped with a hint when its library is not installed."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field

from pasr.hardware.camera.real import CameraHelper
from pasr.hardware.protocols import HardwareNotAvailableError


@dataclass(frozen=True, slots=True)
class Discovery:
    kind: str
    items: list[str] = field(default_factory=list)
    hint: str | None = None


def serial_ports() -> Discovery:
    try:
        from serial.tools import list_ports
    except ImportError:
        return Discovery("serial ports", hint="not installed: uv sync")
    items = [f"{p.device}  {p.description}" for p in list_ports.comports()]
    return Discovery("serial ports", items, None if items else "none found")


def microphones() -> Discovery:
    try:
        from pasr.hardware.microphone.real import SoundDeviceMicrophone

        devices = SoundDeviceMicrophone.list_devices()
    except ImportError:
        return Discovery("microphones", hint="not installed: uv sync")
    items = [f"{index}: {name} ({channels} ch)" for index, name, channels in devices]
    return Discovery("microphones", items, None if items else "none found")


def parse_audio_outputs(report: str) -> list[tuple[str, bool]]:
    """``(name, is default output)`` for each output device in ``system_profiler
    SPAudioDataType`` text (device names are indented 8 spaces, their fields 10)."""
    devices: dict[str, bool] = {}
    name: str | None = None
    for line in report.splitlines():
        stripped = line.strip()
        if line.startswith(" " * 8) and not line.startswith(" " * 9) and stripped.endswith(":"):
            name = stripped[:-1]
        elif name is not None and stripped.startswith("Output Channels"):
            devices.setdefault(name, False)
        elif name is not None and stripped == "Default Output Device: Yes":
            devices[name] = True
    return list(devices.items())


def _audio_report() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["system_profiler", "SPAudioDataType"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def default_audio_output() -> str | None:
    """Where the robot's speech plays: macOS ``say`` and the ohbot library (``afplay``) always
    use the system default output device. ``None`` if unknown (or not macOS)."""
    return next((name for name, default in parse_audio_outputs(_audio_report()) if default), None)


def audio_outputs() -> Discovery:
    if sys.platform != "darwin":
        return Discovery("audio outputs", hint="listed on macOS only")
    devices = parse_audio_outputs(_audio_report())
    items = [f"{name}{'  (macOS default)' if default else ''}" for name, default in devices]
    hint = "the robot speaks on hardware.speaker.output_device, else on the macOS default"
    return Discovery("audio outputs", items, hint if items else "none found")


async def cameras(max_index: int = 4) -> Discovery:
    """Each camera that opens, with its name (macOS) and frame size. Each opens in a helper
    process, as the robot's does (``camera.helper``), so a camera that came back on USB is
    found."""
    if _missing("cv2"):
        return Discovery("cameras", hint="not installed: uv sync")
    items = []
    for index in range(max_index):
        try:
            camera = await CameraHelper.start(index, 0, 0, warmup=0)
        except HardwareNotAvailableError:
            continue
        await camera.stop()
        width, height = camera.size
        items.append(f"{index}: {camera.name + ', ' if camera.name else ''}{width}x{height}")
    hint = None if items else "none found (an iPhone Continuity Camera may shift the indices)"
    return Discovery("cameras", items, hint)


def _missing(module: str) -> bool:
    """Not installed (or blocked, as the tests do), found without importing it."""
    try:
        return importlib.util.find_spec(module) is None
    except ValueError:  # imported already, without a spec
        return False


async def watches(name_prefix: str, timeout_s: float) -> Discovery:
    try:
        import bleak
    except ImportError:
        return Discovery("watches", hint="not installed: uv sync")
    try:
        devices = await bleak.BleakScanner.discover(timeout=timeout_s)
    except Exception as exc:  # Bluetooth off, no permission
        return Discovery("watches", hint=f"scan failed: {exc}")
    items = [f"{d.name}  {d.address}" for d in devices if str(d.name or "").startswith(name_prefix)]
    return Discovery("watches", items, None if items else f"no device named {name_prefix}*")
