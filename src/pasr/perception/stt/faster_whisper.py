"""Local speech-to-text with faster-whisper (Whisper on CTranslate2, CPU, int8).

Weights come from the Hugging Face hub on first use into ``<models_dir>/faster-whisper/`` and
are used offline afterwards. The transcript is used only to parse the reminder and is never
stored (docs/PRIVACY.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import SpeechSegment
from pasr.paths import resolve
from pasr.perception.lazy import LazyEngine
from pasr.settings.tiers import setting

MODEL_RATE = 16000


class FasterWhisperSpeechToText(LazyEngine):
    class Params(BaseModel):
        models_dir: Path = setting(
            Path("models"),
            tier="advanced",
            description="Where the model is downloaded (storage.models_dir by default).",
        )
        model_size: Literal["tiny", "base", "small", "medium"] = setting(
            "base",
            tier="advanced",
            description="Larger models understand more but are slower on the laptop CPU.",
        )
        language: str | None = setting(
            "en",
            tier="advanced",
            description="Spoken language (e.g. 'en', 'de'); empty detects it, which is slower.",
        )
        beam_size: int = setting(
            5, tier="advanced", ge=1, le=10, description="Beam search width; 1 is fastest."
        )
        threads: int = setting(4, tier="advanced", ge=1, le=16, description="CPU threads.")

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params

    def transcribe(self, segment: SpeechSegment) -> str:
        model = self._engine_or_load()
        audio = np.ascontiguousarray(segment.samples, dtype=np.float32)
        if segment.sample_rate != MODEL_RATE:
            duration = len(audio) / segment.sample_rate
            grid = np.linspace(0, duration, int(duration * MODEL_RATE), endpoint=False)
            source = np.arange(len(audio)) / segment.sample_rate
            audio = np.interp(grid, source, audio).astype(np.float32)
        with self._lock:
            pieces, _info = model.transcribe(
                audio, language=self.params.language or None, beam_size=self.params.beam_size
            )
            return " ".join(piece.text.strip() for piece in pieces).strip()

    # --- the only code that talks to faster-whisper ------------------------------------------

    def _load(self) -> Any:
        from faster_whisper import WhisperModel

        root = resolve(self.params.models_dir) / "faster-whisper"
        root.mkdir(parents=True, exist_ok=True)
        return WhisperModel(
            self.params.model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=self.params.threads,
            download_root=str(root),
        )
