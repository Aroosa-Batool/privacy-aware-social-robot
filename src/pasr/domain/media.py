"""In-memory sensor data. These objects are processed and dropped; they are never persisted."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt


def level_db(samples: npt.NDArray[np.float32]) -> float:
    """Loudness of ``samples`` in dBFS (their RMS; -120 for silence)."""
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) if len(samples) else 0.0
    return 20 * math.log10(max(rms, 1e-6))


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

    @property
    def level_db(self) -> float:
        """Loudness in dBFS."""
        return level_db(self.samples)

    @classmethod
    def joined(cls, segments: Sequence[SpeechSegment]) -> SpeechSegment:
        """One segment holding the speech of ``segments`` without the pauses between them;
        ``start`` and ``end`` still span the pauses."""
        if not segments:
            raise ValueError("joining needs at least one speech segment")
        return cls(
            samples=np.concatenate([s.samples for s in segments]),
            sample_rate=segments[0].sample_rate,
            start=segments[0].start,
            end=segments[-1].end,
        )

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
