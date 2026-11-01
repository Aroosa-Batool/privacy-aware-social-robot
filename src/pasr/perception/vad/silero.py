"""Silero VAD (MIT). Model files ship in the pip package; nothing is downloaded.

Silero scores windows of exactly 512 samples at 16 kHz (256 at 8 kHz) and keeps recurrent
state between windows, so the plugin resets that state whenever a chunk does not follow the
previous one , a new listening session starts clean.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import AudioChunk
from pasr.perception.lazy import LazyEngine
from pasr.settings.tiers import setting

logger = logging.getLogger(__name__)

WINDOWS = {16000: 512, 8000: 256}


class SileroVAD(LazyEngine):
    class Params(BaseModel):
        onnx: bool = setting(
            False,
            tier="advanced",
            description="Run the ONNX export on onnxruntime instead of the TorchScript model.",
        )
        threads: int = setting(1, tier="advanced", ge=1, le=16, description="torch CPU threads.")

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params
        self._rate: int | None = None
        self._next_start: datetime | None = None
        self._warned_padding = False

    def speech_probability(self, chunk: AudioChunk) -> float:
        window = WINDOWS.get(chunk.sample_rate)
        if window is None:
            raise ValueError(
                f"Silero VAD supports 8000 or 16000 Hz, not {chunk.sample_rate}: "
                "set hardware.microphone.sample_rate"
            )
        samples = np.ascontiguousarray(chunk.samples, dtype=np.float32)
        if samples.size == 0:
            return 0.0
        if samples.size % window and not self._warned_padding:
            self._warned_padding = True
            logger.warning(
                "audio chunks of %d samples are not a multiple of Silero's %d-sample window; "
                "the last window is zero-padded (set hardware.microphone.chunk_ms=%d)",
                samples.size,
                window,
                window * 1000 // chunk.sample_rate,
            )
        model = self._engine_or_load()
        import torch

        with self._lock:
            if not self._continuous(chunk):
                model.reset_states()
                self._rate = chunk.sample_rate
            self._next_start = chunk.end
            best = 0.0
            for offset in range(0, samples.size, window):
                piece = samples[offset : offset + window]
                if piece.size < window:
                    piece = np.pad(piece, (0, window - piece.size))
                best = max(best, float(model(torch.from_numpy(piece), chunk.sample_rate).item()))
        return best

    def _continuous(self, chunk: AudioChunk) -> bool:
        if self._rate != chunk.sample_rate or self._next_start is None:
            return False
        gap = abs((chunk.start - self._next_start).total_seconds())
        return gap <= chunk.duration_s

    # --- the only code that talks to silero ----------------------------------------------

    def _load(self) -> Any:
        import torch
        from silero_vad import load_silero_vad

        torch.set_num_threads(self.params.threads)
        return load_silero_vad(onnx=self.params.onnx)
