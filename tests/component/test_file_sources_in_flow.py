"""A researcher's WAV file behind the Microphone protocol feeds the real listening pipeline."""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import timedelta

import numpy as np

from fakes import install_fake_soundfile
from pasr.domain.media import AudioChunk
from pasr.hardware.microphone.real import WavFileMicrophone
from pasr.orchestration.runtime import Runtime
from support.clock import VirtualClock


async def test_wav_file_yields_speech_segments(runtime: Runtime, monkeypatch, tmp_path):
    wav = tmp_path / "session.wav"
    wav.write_bytes(b"RIFF")
    rng = np.random.default_rng(0)
    speech = rng.standard_normal(16000) * 0.15  # one second of "speech" ...
    silence = rng.standard_normal(16000) * 0.002  # ... then one second of room noise
    audio = np.concatenate([speech, silence])[:, None].astype(np.float32)
    install_fake_soundfile(monkeypatch, audio, 16000)
    clock = runtime.clock
    microphone = WavFileMicrophone(wav, 16000, 250, clock=clock, realtime=True)

    async def listen():
        until = clock.now() + timedelta(hours=1)
        found = []
        async with aclosing(runtime.ctx.speech_segments(until, microphone=microphone)) as stream:
            async for segment in stream:
                found.append(segment)
        return found

    segments = await clock.drive(listen())
    assert len(segments) == 1
    assert 0.9 <= segments[0].duration_s <= 1.25


class LaggingMicrophone:
    """Chunks stamped by their sample count but arriving at half speed, as when the listening
    loop is starved of the GIL or audio is dropped."""

    def __init__(self, clock: VirtualClock) -> None:
        self.clock = clock

    async def stream(self) -> AsyncGenerator[AudioChunk, None]:
        chunk = timedelta(milliseconds=100)
        stamped = arrives = self.clock.now()
        while True:
            arrives += 2 * chunk
            await self.clock.sleep_until(arrives)
            yield AudioChunk(samples=np.zeros(1600, np.float32), sample_rate=16000, start=stamped)
            stamped += chunk


async def test_listening_ends_on_the_clock_when_audio_lags(runtime: Runtime):
    clock = runtime.clock
    until = clock.now() + timedelta(seconds=10)

    async def listen():
        microphone = LaggingMicrophone(clock)
        async with aclosing(runtime.ctx.speech_segments(until, microphone=microphone)) as stream:
            async for _ in stream:
                pass

    await clock.drive(listen())
    assert clock.now() - until <= timedelta(milliseconds=200)  # not 10 s late
