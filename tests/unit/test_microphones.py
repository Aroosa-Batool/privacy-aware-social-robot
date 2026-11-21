import sys
from contextlib import aclosing
from datetime import timedelta

import numpy as np
import pytest

from fakes import FakeSoundDevice, install_fake_soundfile
from pasr.hardware.microphone.real import SoundDeviceMicrophone, WavFileMicrophone
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.clock import SystemClock
from support.clock import VirtualClock


async def collect(microphone, limit: int | None = None):
    chunks = []
    async with aclosing(microphone.stream()) as stream:
        async for chunk in stream:
            chunks.append(chunk)
            if limit is not None and len(chunks) >= limit:
                break
    return chunks


async def test_sounddevice_chunks_arrive_from_the_callback_thread(monkeypatch, clock):
    world = FakeSoundDevice(chunks=6, overflow_at=2).install(monkeypatch)
    microphone = SoundDeviceMicrophone(None, 16000, 32, clock=clock)
    chunks = await collect(microphone, limit=4)
    (stream,) = world.streams
    assert (stream.samplerate, stream.channels, stream.dtype, stream.blocksize) == (
        16000,
        1,
        "float32",
        512,
    )
    assert stream.device is None and stream.started and stream.stopped and stream.closed
    assert [c.samples.shape for c in chunks] == [(512,)] * 4
    assert all(c.samples.dtype == np.float32 and c.sample_rate == 16000 for c in chunks)
    assert [c.start - clock.now() for c in chunks] == [
        timedelta(milliseconds=32 * i) for i in range(4)
    ]
    assert chunks[1].end == chunks[2].start
    assert microphone.overflows == 1


@pytest.fixture(autouse=True)
def no_retry_pause(monkeypatch):
    monkeypatch.setattr(SoundDeviceMicrophone, "RETRY_DELAY_S", 0.0)


async def test_a_headset_switching_mode_gets_one_retry(monkeypatch, clock):
    world = FakeSoundDevice(failing_opens=1).install(monkeypatch)
    chunks = await collect(SoundDeviceMicrophone(None, 16000, 32, clock=clock), limit=2)
    assert len(chunks) == 2 and world.opens == 2


async def test_sounddevice_failures_and_device_listing(monkeypatch, clock):
    world = FakeSoundDevice(bad_devices=("AirPods",)).install(monkeypatch)
    with pytest.raises(HardwareNotAvailableError, match="microphone 'AirPods' could not be opened"):
        await collect(SoundDeviceMicrophone("AirPods", 16000, 32, clock=clock), limit=1)
    assert world.opens == 2  # tried twice
    FakeSoundDevice(failing_opens=2).install(monkeypatch)
    with pytest.raises(HardwareNotAvailableError, match=r"default input \(AirPods Pro\)"):
        await collect(SoundDeviceMicrophone(None, 16000, 32, clock=clock), limit=1)
    assert SoundDeviceMicrophone.list_devices() == [
        (0, "MacBook Air Microphone", 1),
        (2, "USB Audio", 2),
        (3, "AirPods Pro", 1),
    ]
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    with pytest.raises(HardwareNotAvailableError, match="not installed: uv sync"):
        await collect(SoundDeviceMicrophone(None, 16000, 32, clock=clock), limit=1)


async def test_wav_file_is_chunked_mixed_to_mono_and_ends(monkeypatch, tmp_path):
    wav = tmp_path / "room.wav"
    wav.write_bytes(b"RIFF")
    stereo = np.stack([np.full(16000 + 100, 0.2), np.full(16000 + 100, 0.4)], axis=1).astype(
        np.float32
    )
    install_fake_soundfile(monkeypatch, stereo, 16000)
    clock = SystemClock()
    microphone = WavFileMicrophone(wav, 16000, 250, clock=clock, realtime=False)
    t0 = clock.now()
    chunks = await collect(microphone)
    assert len(chunks) == 4  # the trailing 100 samples are dropped
    assert all(np.allclose(c.samples, 0.3) and c.samples.dtype == np.float32 for c in chunks)
    assert chunks[0].start >= t0 and chunks[3].start - chunks[0].start == timedelta(
        milliseconds=750
    )


async def test_wav_file_paces_on_the_clock(monkeypatch, tmp_path, clock: VirtualClock):
    wav = tmp_path / "room.wav"
    wav.write_bytes(b"RIFF")
    install_fake_soundfile(monkeypatch, np.zeros((16000, 1), dtype=np.float32), 16000)
    microphone = WavFileMicrophone(wav, 16000, 250, clock=clock, realtime=True)
    before = clock.now()
    chunks = await clock.drive(collect(microphone))
    assert len(chunks) == 4 and clock.now() - before == timedelta(seconds=1)


async def test_wav_file_errors(monkeypatch, tmp_path, clock):
    with pytest.raises(HardwareNotAvailableError, match="not found"):
        install_fake_soundfile(monkeypatch, np.zeros((10, 1)), 16000)
        await collect(WavFileMicrophone(tmp_path / "missing.wav", 16000, 32, clock=clock))
    wav = tmp_path / "x.wav"
    wav.write_bytes(b"RIFF")
    install_fake_soundfile(monkeypatch, np.zeros((10, 1)), 44100)
    with pytest.raises(HardwareNotAvailableError, match="ffmpeg -i x.wav -ar 16000 -ac 1"):
        await collect(WavFileMicrophone(wav, 16000, 32, clock=clock))
    monkeypatch.setitem(sys.modules, "soundfile", None)
    with pytest.raises(HardwareNotAvailableError, match="not installed: uv sync"):
        await collect(WavFileMicrophone(wav, 16000, 32, clock=clock))
