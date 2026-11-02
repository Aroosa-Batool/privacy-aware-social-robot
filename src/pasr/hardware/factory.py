from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pasr.hardware.camera.real import ImageFolderCamera, OpenCVCamera
from pasr.hardware.head.real import OhbotHead
from pasr.hardware.microphone.real import SoundDeviceMicrophone, WavFileMicrophone
from pasr.hardware.ohbot_driver import NodPositions, TurnPositions
from pasr.hardware.protocols import Camera, Microphone, RobotHead, Speaker, Watch
from pasr.hardware.speaker.real import MacSaySpeaker, OhbotSpeaker
from pasr.hardware.watch.bangle import BangleWatch, BleakTransport
from pasr.orchestration.clock import Clock
from pasr.settings.schema import HardwareSettings


@dataclass(slots=True)
class HardwareBundle:
    head: RobotHead
    speaker: Speaker
    camera: Camera
    microphone: Microphone
    watch: Watch

    async def connect(self, *, watch: bool = True) -> None:
        """``watch=False`` skips the watch (enrolment, calibration); ``BangleWatch`` connects
        lazily before its first request anyway."""
        await self.head.connect()
        if watch:
            await self.watch.connect()

    async def close(self) -> None:
        await self.camera.close()
        await self.watch.disconnect()
        await self.head.close()


def build_hardware(
    settings: HardwareSettings,
    *,
    clock: Clock,
    on_watch_address: Callable[[str], None] | None = None,
) -> HardwareBundle:
    """The configured devices. Nothing is opened here; libraries load on connect/open.
    ``on_watch_address`` receives the watch's Bluetooth address once discovered, so the
    runtime can cache it in settings and skip scanning next time."""
    o = settings.ohbot
    head: RobotHead = OhbotHead(
        o.port,
        turns=TurnPositions(o.turn_left, o.turn_front, o.turn_right),
        nods=NodPositions(o.nod_level, o.nod_up, o.nod_down),
        move_seconds=o.move_seconds,
    )

    speaker: Speaker
    if settings.speaker.backend == "ohbot":
        speaker = OhbotSpeaker(o.port, output_device=settings.speaker.output_device)
    else:
        speaker = MacSaySpeaker(settings.speaker.voice, settings.speaker.output_device)

    cam = settings.camera
    camera: Camera
    if cam.source == "images":
        assert cam.image_dir is not None  # enforced by the settings validator
        camera = ImageFolderCamera(cam.image_dir, clock=clock)
    else:
        camera = OpenCVCamera(
            cam.index,
            cam.width,
            cam.height,
            clock=clock,
            name=cam.name,
            warmup_frames=cam.warmup_frames,
        )

    mic = settings.microphone
    microphone: Microphone
    if mic.source == "wav":
        assert mic.wav_path is not None  # enforced by the settings validator
        microphone = WavFileMicrophone(
            mic.wav_path, mic.sample_rate, mic.chunk_ms, clock=clock, realtime=mic.wav_realtime
        )
    else:
        microphone = SoundDeviceMicrophone(mic.device, mic.sample_rate, mic.chunk_ms, clock=clock)

    w = settings.watch
    watch: Watch = BangleWatch(
        BleakTransport(
            w.name_prefix,
            w.address,
            w.reconnect_attempts,
            scan_timeout_s=w.scan_timeout_seconds,
            on_address_found=on_watch_address,
        )
    )
    return HardwareBundle(head, speaker, camera, microphone, watch)
