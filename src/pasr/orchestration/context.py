from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from concurrent.futures import Executor
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from functools import partial

from pasr.domain.media import SpeechSegment
from pasr.hardware.factory import HardwareBundle
from pasr.hardware.protocols import Microphone
from pasr.live.feed import LiveFeed
from pasr.orchestration.clock import Clock
from pasr.orchestration.events import EventBus
from pasr.perception.bundle import PerceptionBundle
from pasr.perception.segmenter import SpeechSegmenter
from pasr.settings.schema import Settings
from pasr.storage.repos import Repositories


@dataclass(slots=True)
class RobotContext:
    """Everything an app or flow needs. ``settings`` may be swapped live by the runtime;
    a flow reads it once when it starts."""

    settings: Settings
    clock: Clock
    hardware: HardwareBundle
    perception: PerceptionBundle
    repos: Repositories
    bus: EventBus
    live: LiveFeed
    executor: Executor | None = None

    async def compute[T](self, fn: Callable[..., T], *args: object) -> T:
        """Run blocking perception work off the event loop (inline without an executor)."""
        if self.executor is None:
            return fn(*args)
        return await asyncio.get_running_loop().run_in_executor(self.executor, partial(fn, *args))

    def segmenter(self, *, min_silence_ms: int | None = None) -> SpeechSegmenter:
        vad = self.settings.vad
        return SpeechSegmenter(
            speech_threshold=vad.speech_threshold,
            min_speech_ms=vad.min_speech_ms,
            min_silence_ms=vad.min_silence_ms if min_silence_ms is None else min_silence_ms,
            max_segment_seconds=vad.max_segment_seconds,
        )

    async def speech_segments(
        self,
        until: datetime,
        *,
        microphone: Microphone | None = None,
        min_silence_ms: int | None = None,
    ) -> AsyncGenerator[SpeechSegment, None]:
        """Speech segments heard on the microphone (or another audio source, e.g. a WAV file)
        until ``until``; a pause of ``min_silence_ms`` (``vad.min_silence_ms`` by default) ends
        one. Wrap in ``aclosing``."""
        segmenter = self.segmenter(min_silence_ms=min_silence_ms)
        vad = self.perception.vad
        threshold = self.settings.vad.speech_threshold
        source = microphone or self.hardware.microphone
        async with aclosing(source.stream()) as chunks:
            async for chunk in chunks:
                # A chunk arrives once recorded, at its end. Its start counts samples, so it falls
                # behind the clock when this loop lags or audio is dropped; the clock then ends
                # listening on time anyway.
                if chunk.start >= until or self.clock.now() >= until + (chunk.end - chunk.start):
                    break
                probability = await self.compute(vad.speech_probability, chunk)
                self.live.audio(chunk, probability, threshold)
                for segment in segmenter.push(chunk, probability):
                    yield segment
        for segment in segmenter.flush():
            yield segment
