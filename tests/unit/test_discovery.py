import sys

import pytest

from fakes import BLEDevice, FakeBleak, FakeCameraHelpers, FakeSoundDevice
from pasr.hardware import discovery


async def test_each_probe_hints_when_its_library_is_missing(monkeypatch):
    for module in ("serial.tools.list_ports", "serial", "sounddevice", "cv2", "bleak"):
        monkeypatch.setitem(sys.modules, module, None)
    for probe in (discovery.serial_ports, discovery.microphones):
        assert probe().hint == "not installed: uv sync"
    assert (await discovery.cameras()).hint == "not installed: uv sync"


async def test_probes_list_what_they_find(monkeypatch, camera_helpers: FakeCameraHelpers):
    FakeSoundDevice().install(monkeypatch)
    camera_helpers.plan({"open_indices": [1], "cameras": ["MacBook Air Camera", "HD Webcam C615"]})
    world = FakeBleak([BLEDevice("Bangle.js 1a2b", "UUID-1"), BLEDevice("AirPods", "x")]).install(
        monkeypatch
    )

    async def discover(**kwargs):
        return world.devices

    world_module = sys.modules["bleak"]
    world_module.BleakScanner.discover = discover  # type: ignore[attr-defined]
    assert discovery.microphones().items == [
        "0: MacBook Air Microphone (1 ch)",
        "2: USB Audio (2 ch)",
        "3: AirPods Pro (1 ch)",
    ]
    assert (await discovery.cameras()).items == ["1: HD Webcam C615, 0x0"]  # each in a helper
    found = await discovery.watches("Bangle.js", 1.0)
    assert found.items == ["Bangle.js 1a2b  UUID-1"] and found.hint is None
    assert (await discovery.watches("Pebble", 1.0)).hint == "no device named Pebble*"


@pytest.mark.parametrize("prefix", ["Bangle.js"])
async def test_watch_scan_failure_is_a_hint(monkeypatch, prefix):
    FakeBleak(bluetooth_off=True).install(monkeypatch)

    async def discover(**kwargs):
        raise RuntimeError("Bluetooth is off")

    sys.modules["bleak"].BleakScanner.discover = discover  # type: ignore[attr-defined]
    assert (await discovery.watches(prefix, 1.0)).hint == "scan failed: Bluetooth is off"


SYSTEM_PROFILER = """Audio:

    Devices:

        iPhone Microphone:

          Input Channels: 1
          Transport: Unknown

        MacBook Air Speakers:

          Default System Output Device: Yes
          Output Channels: 2
          Transport: Built-in

        AirPods Pro:

          Default Output Device: Yes
          Input Channels: 1
          Output Channels: 2
          Transport: Bluetooth
"""


def test_audio_outputs_mark_where_the_robot_speaks(monkeypatch):
    assert discovery.parse_audio_outputs(SYSTEM_PROFILER) == [
        ("MacBook Air Speakers", False),
        ("AirPods Pro", True),
    ]
    monkeypatch.setattr(discovery, "_audio_report", lambda: SYSTEM_PROFILER)
    monkeypatch.setattr(discovery.sys, "platform", "darwin")
    assert discovery.default_audio_output() == "AirPods Pro"
    found = discovery.audio_outputs()
    assert found.items == ["MacBook Air Speakers", "AirPods Pro  (macOS default)"]
    assert "hardware.speaker.output_device" in (found.hint or "")
    assert discovery.parse_audio_outputs("") == []
