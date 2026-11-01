"""In-memory sensor data. These objects are processed and dropped; they are never persisted."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    image: npt.NDArray[np.uint8]
    """HxWx3 uint8 in **BGR** order (OpenCV's convention, which InsightFace also expects)."""
    captured_at: datetime


@dataclass(frozen=True, slots=True, eq=False)
class AudioChunk:
    samples: npt.NDArray[np.float32]
    sample_rate: int
    start: datetime

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration_s)


@dataclass(frozen=True, slots=True, eq=False)
class SpeechSegment:
    samples: npt.NDArray[np.float32]
    sample_rate: int
    start: datetime
    end: datetime

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()

    @classmethod
    def from_chunks(cls, chunks: Sequence[AudioChunk]) -> SpeechSegment:
        if not chunks:
            raise ValueError("a speech segment needs at least one chunk")
        return cls(
            samples=np.concatenate([c.samples for c in chunks]),
            sample_rate=chunks[0].sample_rate,
            start=chunks[0].start,
            end=chunks[-1].end,
        )
