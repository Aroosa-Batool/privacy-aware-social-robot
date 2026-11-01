"""Real microphones: the laptop microphone through ``sounddevice``, and a researcher-supplied
WAV file for offline experiments. Audio is never written to disk."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pasr.domain.media import AudioChunk
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.orchestration.clock import Clock
from pasr.paths import resolve

logger = logging.getLogger(__name__)


class SoundDeviceMicrophone:
    """The PortAudio callback runs on its own thread and hands each chunk to the event loop
    with ``call_soon_threadsafe``. Chunk timestamps come from the sample count, so they are
    monotonic within a stream.

    Opening is retried once: Bluetooth headsets (AirPods) switch profile when their microphone
    is first used, and PortAudio's first open can fail meanwhile.
    """

    RETRY_DELAY_S = 0.5

    def __init__(self, device: str | None, sample_rate: int, chunk_ms: int, *, clock: Clock):
        self.device = device or None
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.clock = clock
        self.overflows = 0

    async def stream(self) -> AsyncGenerator[AudioChunk, None]:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise HardwareNotAvailableError("sounddevice is not installed: uv sync") from exc
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[npt.NDArray[np.float32]] = asyncio.Queue()
        samples_per_chunk = self.sample_rate * self.chunk_ms // 1000

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status and getattr(status, "input_overflow", False):
                self.overflows += 1
                if self.overflows % 10 == 1:
                    logger.warning(
                        "the microphone dropped some audio (%d overflows so far)", self.overflows
                    )
            samples = np.array(indata[:, 0], dtype=np.float32, copy=True)
            loop.call_soon_threadsafe(queue.put_nowait, samples)

        def open_stream() -> Any:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=samples_per_chunk,
                device=self.device,
                callback=callback,
            )
            stream.start()
            return stream

        try:
            stream = open_stream()
        except Exception as first:
            logger.info("microphone did not open (%s); trying once more", first)
            await asyncio.sleep(self.RETRY_DELAY_S)
            try:
                stream = open_stream()
            except Exception as exc:
                raise HardwareNotAvailableError(
                    f"microphone {self._name(sd)} could not be opened ({exc}). Choose a fixed "
                    "microphone in hardware.microphone.device (Setup page lists them; AirPods "
                    "and iPhones come and go), and check that the app running pasr may use "
                    "the microphone"
                ) from exc
        started = self.clock.now()
        produced = 0
        try:
            while True:
                samples = await queue.get()
                start = started + timedelta(seconds=produced / self.sample_rate)
                produced += len(samples)
                yield AudioChunk(samples=samples, sample_rate=self.sample_rate, start=start)
        finally:
            await asyncio.to_thread(_stop_stream, stream)

    def _name(self, sd: Any) -> str:
        if self.device:
            return repr(self.device)
        try:
            return f"default input ({sd.query_devices(kind='input')['name']})"
        except Exception:
            return "default input"

    @staticmethod
    def list_devices() -> list[tuple[int, str, int]]:
        """``(index, name, input channels)`` for every input device."""
        import sounddevice as sd

        return [
            (index, str(device["name"]), int(device["max_input_channels"]))
            for index, device in enumerate(sd.query_devices())
            if int(device["max_input_channels"]) > 0
        ]


def _stop_stream(stream: Any) -> None:
    stream.stop()
    stream.close()


class WavFileMicrophone:
    """A researcher-supplied WAV file behind the ``Microphone`` protocol (ADR 0002). Read-only,
    and the stream ends with the file. With ``realtime`` the chunks are paced on the clock so the
    file behaves like a room; otherwise they arrive as fast as the consumer takes them."""

    def __init__(
        self,
        path: Path,
        sample_rate: int,
        chunk_ms: int,
        *,
        clock: Clock,
        realtime: bool = True,
    ) -> None:
        self.path = path
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.clock = clock
        self.realtime = realtime

    async def stream(self) -> AsyncGenerator[AudioChunk, None]:
        mono = await asyncio.to_thread(self._read)
        n = self.sample_rate * self.chunk_ms // 1000
        chunk = timedelta(milliseconds=self.chunk_ms)
        start = self.clock.now()
        for offset in range(0, len(mono) - n + 1, n):
            if self.realtime:
                await self.clock.sleep_until(start + chunk)  # a chunk is ready once "recorded"
            else:
                await asyncio.sleep(0)
            yield AudioChunk(
                samples=mono[offset : offset + n].copy(),
                sample_rate=self.sample_rate,
                start=start,
            )
            start += chunk

    def _read(self) -> npt.NDArray[np.float32]:
        try:
            import soundfile
        except ImportError as exc:
            raise HardwareNotAvailableError("soundfile is not installed: uv sync") from exc
        path = resolve(self.path)
        if not path.is_file():
            raise HardwareNotAvailableError(f"WAV file not found: {path}")
        data, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
        if int(rate) != self.sample_rate:
            raise HardwareNotAvailableError(
                f"{path.name} is {rate} Hz but hardware.microphone.sample_rate is "
                f"{self.sample_rate}; resample it first: "
                f"ffmpeg -i {path.name} -ar {self.sample_rate} -ac 1 out.wav"
            )
        samples = np.asarray(data, dtype=np.float32)
        mono = samples.mean(axis=1) if samples.shape[1] > 1 else samples[:, 0]
        return np.ascontiguousarray(mono, dtype=np.float32)
