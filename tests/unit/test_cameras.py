import logging
import sys

import numpy as np
import pytest

from fakes import FakeCameraHelpers, FakeCv2
from pasr.hardware.camera.real import ImageFolderCamera, OpenCVCamera
from pasr.hardware.protocols import HardwareNotAvailableError
from support.clock import VirtualClock


def silent_camera(clock: VirtualClock, **options) -> OpenCVCamera:
    """A camera whose stalls and reconnects take a moment, not seconds."""
    options = {"warmup_frames": 0, "stall_seconds": 0.05, "reconnect_seconds": 1.0} | options
    return OpenCVCamera(0, 640, 480, clock=clock, **options)


async def test_the_camera_runs_in_a_helper_process(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera = OpenCVCamera(0, 320, 240, clock=clock, warmup_frames=3)
    with pytest.raises(RuntimeError, match="not open"):
        await camera.grab()
    assert camera_helpers.started == 0  # nothing touched before open()
    await camera.open()
    await camera.open()  # idempotent
    frame = await camera.grab()
    assert frame.image.shape == (480, 640, 3) and frame.image.dtype == np.uint8
    assert frame.image.flags.writeable
    assert frame.captured_at == clock.now()
    await camera.close()
    await camera.close()
    assert camera_helpers.started == 1
    (capture,) = camera_helpers.report(0)
    assert capture["backend"] == (FakeCv2.CAP_AVFOUNDATION if sys.platform == "darwin" else 0)
    assert capture["props"] == {"3": 320, "4": 240}  # width, height
    assert capture["reads"] == 4 and capture["released"]  # 3 warm-up frames, then one


async def test_a_camera_that_cannot_be_opened(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera_helpers.plan({"open_indices": [1]})
    with pytest.raises(HardwareNotAvailableError, match="camera 0 could not be opened"):
        await OpenCVCamera(0, 640, 480, clock=clock).open()
    camera_helpers.plan({"missing": True})
    with pytest.raises(HardwareNotAvailableError, match="OpenCV is not installed: uv sync"):
        await OpenCVCamera(0, 640, 480, clock=clock).open()


async def test_the_head_camera_is_found_by_name(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera_helpers.plan(
        {"open_indices": [0, 1], "cameras": ["MacBook Air Camera", "HD Webcam C615"]},
        {"open_indices": [0], "cameras": ["MacBook Air Camera"]},  # the C615 is unplugged
    )
    camera = OpenCVCamera(0, 640, 480, clock=clock, name="c615", warmup_frames=0)
    await camera.open()
    await camera.grab()
    await camera.close()
    assert camera_helpers.report(0)[0]["index"] == 1  # not index 0, the laptop's camera
    with pytest.raises(
        HardwareNotAvailableError,
        match=r"no camera named like 'c615' is connected \(found: MacBook Air Camera\)",
    ):
        await camera.open()
    assert camera_helpers.report(1) == []  # the laptop's camera was never opened instead


def test_names_are_found_on_macos_only(monkeypatch: pytest.MonkeyPatch):
    from pasr.hardware.camera import helper

    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(HardwareNotAvailableError, match="macOS only"):
        helper.find(0, "C615")
    assert helper.find(2, "") == (2, "")  # by index, its name unknown


async def test_a_short_stall_is_waited_out(camera_helpers: FakeCameraHelpers, clock: VirtualClock):
    camera_helpers.plan({"stalled_reads": [2, 5]})
    camera = silent_camera(clock, stall_seconds=5.0)
    await camera.open()
    await camera.grab()
    await camera.grab()  # reads 2–4 fail, the 5th arrives
    await camera.close()
    assert camera_helpers.started == 1
    assert camera_helpers.report(0)[0]["reads"] == 5


async def test_a_camera_that_drops_off_is_reconnected_by_a_fresh_helper(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)
    camera_helpers.plan({"fail_reads_after": 1}, {})  # the first helper's camera goes silent
    camera = silent_camera(clock)
    await camera.open()
    await camera.grab()
    frame = await camera.grab()  # from a fresh helper, which finds the camera again
    assert frame.image.shape == (480, 640, 3)
    assert camera_helpers.started == 2
    assert camera_helpers.report(0)[0]["released"]  # the silent one was closed properly
    assert "camera 0 sent no frame for 0 s: reconnecting it" in caplog.text
    assert "camera 0 is back" in caplog.text
    await camera.close()
    assert camera_helpers.report(1)[0]["released"]


async def test_a_helper_that_dies_is_replaced(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera_helpers.plan({"exit_at_read": 2}, {})
    camera = silent_camera(clock)
    await camera.open()
    await camera.grab()
    await camera.grab()  # the helper died on its second read
    await camera.close()
    assert camera_helpers.started == 2 and camera_helpers.report(0) is None


async def test_a_camera_that_stays_away_says_to_check_its_cable(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera_helpers.plan({"fail_reads_after": 1}, {"open_indices": []})  # unplugged for good
    camera = silent_camera(clock)
    await camera.open()
    await camera.grab()
    with pytest.raises(
        HardwareNotAvailableError,
        match=r"stopped sending frames and did not come back within 1 s \(camera 0 could not "
        r"be opened.*Check its USB cable",
    ):
        await camera.grab()
    await camera.close()
    assert camera_helpers.started >= 2


async def test_a_camera_that_never_sends_a_frame_may_be_the_wrong_one(
    camera_helpers: FakeCameraHelpers, clock: VirtualClock
):
    camera_helpers.plan({"fail_reads_after": 0})
    camera = silent_camera(clock)
    await camera.open()
    with pytest.raises(
        HardwareNotAvailableError,
        match=r"sent no frame, even after reconnecting for 1 s .*Is it the head camera",
    ):
        await camera.grab()
    await camera.close()


async def test_image_folder_camera_cycles_in_name_order(monkeypatch, clock, tmp_path):
    for name in ("b.jpg", "a.PNG", "notes.txt", "c.bmp"):
        (tmp_path / name).write_bytes(b"")
    images = {
        name: np.full((2, 2, 3), i, dtype=np.uint8) for i, name in enumerate(["a.PNG", "b.jpg"])
    }
    FakeCv2(images=images).install(monkeypatch)
    camera = ImageFolderCamera(tmp_path, clock=clock)
    await camera.open()
    seen = [int((await camera.grab()).image[0, 0, 0]) for _ in range(2)]
    assert seen == [0, 1]
    with pytest.raises(HardwareNotAvailableError, match="could not read image"):
        await camera.grab()  # c.bmp is unreadable
    assert int((await camera.grab()).image[0, 0, 0]) == 0  # cycles
    await camera.close()
    with pytest.raises(RuntimeError):
        await camera.grab()

    with pytest.raises(HardwareNotAvailableError, match="no images"):
        await ImageFolderCamera(tmp_path / "empty", clock=clock).open()
