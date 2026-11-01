"""Resemblyzer d-vectors (256-d, MIT). Light, and its weights ship inside the package."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import SpeechSegment
from pasr.domain.models import Embedding
from pasr.perception.lazy import LazyEngine
from pasr.settings.tiers import setting

MODEL_RATE = 16000


class ResemblyzerEmbedder(LazyEngine):
    extra = "resemblyzer"
    recommended_threshold: ClassVar[float | None] = 0.75
    """Cosine similarity starting point for d-vectors; calibrate with `pasr calibrate`."""

    class Params(BaseModel):
        threads: int = setting(2, tier="advanced", ge=1, le=16, description="torch CPU threads.")
        min_trimmed_seconds: float = setting(
            0.4,
            tier="advanced",
            ge=0,
            le=5,
            description="If silence trimming leaves less speech than this, embed the raw audio.",
        )

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params
        self.model = "resemblyzer-dvector"

    def embed(self, segment: SpeechSegment) -> Embedding:
        encoder = self._engine_or_load()
        from resemblyzer import preprocess_wav

        samples = np.ascontiguousarray(segment.samples, dtype=np.float32)
        wav = preprocess_wav(samples, source_sr=segment.sample_rate)
        if len(wav) < self.params.min_trimmed_seconds * MODEL_RATE and (
            segment.sample_rate == MODEL_RATE
        ):
            wav = samples
        with self._lock:
            vector = encoder.embed_utterance(wav)
        return Embedding.of(vector, self.model)

    # --- the only code that talks to resemblyzer -----------------------------------------

    def _load(self) -> Any:
        import torch
        from resemblyzer import VoiceEncoder

        torch.set_num_threads(self.params.threads)
        return VoiceEncoder("cpu", verbose=False)
