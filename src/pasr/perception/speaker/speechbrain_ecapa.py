"""SpeechBrain ECAPA-TDNN speaker embeddings (192-d), 16 kHz input, CPU.

Weights come from the Hugging Face hub on first use into ``<models_dir>/speechbrain/`` and are
used offline afterwards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import SpeechSegment
from pasr.domain.models import Embedding
from pasr.paths import resolve
from pasr.perception.lazy import LazyEngine
from pasr.settings.tiers import setting

MODEL_RATE = 16000


class SpeechBrainEcapaEmbedder(LazyEngine):
    recommended_threshold: ClassVar[float | None] = 0.35
    """Cosine similarity starting point for ECAPA embeddings; calibrate with `pasr calibrate`."""

    class Params(BaseModel):
        models_dir: Path = setting(
            Path("models"),
            tier="advanced",
            description="Where the model is downloaded (storage.models_dir by default).",
        )
        source: str = setting(
            "speechbrain/spkrec-ecapa-voxceleb",
            tier="advanced",
            min_length=1,
            description="Hugging Face model id (changing it means re-enrolling the owner).",
        )
        threads: int = setting(2, tier="advanced", ge=1, le=16, description="torch CPU threads.")

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params
        self.model = f"speechbrain-{params.source.rsplit('/', 1)[-1]}"

    def embed(self, segment: SpeechSegment) -> Embedding:
        encoder = self._engine_or_load()
        import torch

        wav = torch.from_numpy(np.ascontiguousarray(segment.samples, dtype=np.float32))
        if segment.sample_rate != MODEL_RATE:
            import torchaudio

            wav = torchaudio.functional.resample(wav, segment.sample_rate, MODEL_RATE)
        with self._lock, torch.inference_mode():
            output = encoder.encode_batch(wav.unsqueeze(0))
        return Embedding.of(output.squeeze().cpu().numpy(), self.model)

    # --- the only code that talks to speechbrain -----------------------------------------

    def _load(self) -> Any:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier

        torch.set_num_threads(self.params.threads)
        savedir = (
            resolve(self.params.models_dir)
            / "speechbrain"
            / self.model.removeprefix("speechbrain-")
        )
        return EncoderClassifier.from_hparams(
            source=self.params.source, savedir=str(savedir), run_opts={"device": "cpu"}
        )
