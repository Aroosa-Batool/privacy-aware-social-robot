from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import AudioChunk
from pasr.settings.tiers import setting


class EnergyVAD:
    """Speech probability from RMS loudness: 0.5 exactly at ``rms_threshold``."""

    class Params(BaseModel):
        rms_threshold: float = setting(
            0.02,
            tier="advanced",
            gt=0,
            le=1,
            description="RMS level (full scale = 1.0) treated as the speech boundary.",
        )
        steepness: float = setting(
            4.0,
            tier="advanced",
            gt=0,
            le=50,
            description="How sharply probability rises around the threshold.",
        )

    def __init__(self, params: Params) -> None:
        self.params = params

    def speech_probability(self, chunk: AudioChunk) -> float:
        if chunk.samples.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(np.square(chunk.samples, dtype=np.float64))))
        if rms == 0.0:
            return 0.0
        return float(1.0 / (1.0 + (self.params.rms_threshold / rms) ** self.params.steepness))
