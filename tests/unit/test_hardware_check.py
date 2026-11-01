"""The device check against stand-in devices (they sleep on the virtual clock)."""

from conftest import stand_ins
from pasr.hardware.check import check_devices
from pasr.hardware.factory import HardwareBundle
from support.clock import VirtualClock


async def test_every_device_is_exercised(make_settings, clock: VirtualClock):
    settings = make_settings(hardware={"speaker": {"output_device": "MacBook Air Speakers"}})
    hardware = stand_ins(settings, clock)
    reports = await clock.drive(check_devices(settings, hardware=hardware))
    assert [r.device for r in reports] == ["ohbot", "speaker", "camera", "microphone", "watch"]
    assert all(r.ok for r in reports), reports
    assert "through 'MacBook Air Speakers'" in reports[1].detail
    room = hardware.room
    assert room.spoken[-1].text == "Robot check."
    assert room.camera_grabs == 1 and not room.camera_on  # camera released again


async def test_failures_become_reports(settings, clock: VirtualClock):
    hardware = stand_ins(settings, clock)

    class BrokenCamera:
        async def open(self):
            raise OSError("no such device")

        async def close(self):
            pass

        async def grab(self):
            raise AssertionError

    broken = HardwareBundle(
        hardware.head, hardware.speaker, BrokenCamera(), hardware.microphone, hardware.watch
    )
    (report,) = await clock.drive(check_devices(settings, only=["camera"], hardware=broken))
    assert not report.ok and "OSError" in report.detail

    (report,) = await clock.drive(check_devices(settings, only=["camera"], hardware=hardware))
    assert report.ok and report.detail == "frame 320x240"


async def test_microphone_check_reads_a_few_chunks(settings, clock: VirtualClock):
    hardware = stand_ins(settings, clock)
    (report,) = await clock.drive(check_devices(settings, only=["microphone"], hardware=hardware))
    assert report.ok and report.detail.startswith("16000 Hz, 5 chunks")


async def test_a_found_watch_address_is_saved(make_settings, clock: VirtualClock, monkeypatch):
    from pasr.paths import resolve
    from pasr.settings.loader import read_overrides

    settings = make_settings()
    hardware = stand_ins(settings, clock)
    seen = {}

    def build(hardware_settings, *, clock, on_watch_address=None):
        seen["callback"] = on_watch_address
        return hardware

    monkeypatch.setattr("pasr.hardware.check.build_hardware", build)
    await clock.drive(check_devices(settings, only=["camera"]))
    seen["callback"]("5909CB78-E0E1")
    overrides = read_overrides(resolve(settings.storage.data_dir))
    assert overrides == {"hardware": {"watch": {"address": "5909CB78-E0E1"}}}
