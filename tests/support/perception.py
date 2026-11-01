"""Stand-in perception plugins for the tests: identities come from the ``Room`` instead of
from models. Each tag maps to a fixed random unit vector, so the same person always gets a
near-identical embedding and different people are almost orthogonal , thresholds behave like
they do with real models."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
from pydantic import BaseModel

from pasr.domain.media import Frame, SpeechSegment
from pasr.domain.models import Embedding
from pasr.perception import registry
from pasr.perception.protocols import FaceObservation
from pasr.perception.registry import PluginKind, PluginSpec
from pasr.settings.tiers import setting
from support import room as room_module
from support.room import Utterance

STAND_IN = "stand_in"

STAND_IN_PERCEPTION: dict[str, Any] = {
    "face": {"plugin": STAND_IN},
    "speaker": {"plugin": STAND_IN},
    "stt": {"plugin": STAND_IN},
    "vad": {"plugin": "energy"},
    "sensitivity": {"plugin": "keyword"},
}
"""Tests never load the real models: identities come from the test room, sensitivity from the
keyword lists."""


def _fixed_direction(key: str, dim: int) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    vector = np.random.default_rng(seed).standard_normal(dim)
    return vector / np.linalg.norm(vector)


def identity_embedding(
    tag: str | None,
    *,
    model: str,
    dim: int,
    noise: float,
    rng: np.random.Generator,
    clarity: float = 1.0,
    view: str = "",
) -> Embedding:
    """``clarity`` below 1 (a cut-off or turned-away face) pulls the embedding towards a fixed
    unclear ``view`` of the person: the same in every frame with that view, less and less like
    them."""
    if tag is None:
        base = rng.standard_normal(dim)  # unknown speaker: a fresh random identity
        base /= np.linalg.norm(base)
    else:
        base = _fixed_direction(f"{model}:{tag}", dim)
        if clarity < 1:
            weight = clarity**2
            unclear = _fixed_direction(f"{model}:{tag}:unclear:{view}", dim)
            base = weight * base + (1 - weight) * unclear
            base /= np.linalg.norm(base)
    return Embedding.of(base + noise * rng.standard_normal(dim) / np.sqrt(dim), model)


def _voice(segment: SpeechSegment) -> Utterance | None:
    """Who was speaking in the middle of ``segment``, according to the current room."""
    room = room_module.CURRENT
    if room is None:
        return None
    return room.voice_at(segment.start + (segment.end - segment.start) / 2)


class FakeFaceEmbedder:
    """Returns one face per person the fake camera placed in the frame, with the box and
    landmarks it placed them at; a partly hidden face gets a lower score."""

    class Params(BaseModel):
        noise: float = setting(
            0.3,
            tier="advanced",
            ge=0,
            le=5,
            description="Embedding noise; higher values make people harder to tell apart.",
        )
        dim: int = setting(128, tier="advanced", ge=8, le=1024, description="Embedding size.")

    def __init__(self, params: Params) -> None:
        self.params = params
        self.model = f"fake-face-{params.dim}"
        self._rng = np.random.default_rng()

    def detect_and_embed(self, frame: Frame) -> list[FaceObservation]:
        return [
            FaceObservation(
                identity_embedding(
                    face.tag,
                    model=self.model,
                    dim=self.params.dim,
                    noise=self.params.noise,
                    rng=self._rng,
                    clarity=face.clarity,
                    view=face.view,
                ),
                score=0.95 * face.clarity,
                box=face.box,
                landmarks=face.landmarks,
            )
            for face in getattr(frame, "faces", ())
        ]


class FakeSpeakerEmbedder:
    """Embeds the simulated speaker of a segment; unknown speakers get a random identity."""

    class Params(BaseModel):
        noise: float = setting(
            0.3,
            tier="advanced",
            ge=0,
            le=5,
            description="Embedding noise; higher values make voices harder to tell apart.",
        )
        dim: int = setting(192, tier="advanced", ge=8, le=1024, description="Embedding size.")

    def __init__(self, params: Params) -> None:
        self.params = params
        self.model = f"fake-voice-{params.dim}"
        self._rng = np.random.default_rng()

    def embed(self, segment: SpeechSegment) -> Embedding:
        return identity_embedding(
            _voice(segment).speaker if _voice(segment) else None,
            model=self.model,
            dim=self.params.dim,
            noise=self.params.noise,
            rng=self._rng,
        )


class FakeSpeechToText:
    """Returns the text the simulated speaker said."""

    class Params(BaseModel):
        pass

    def __init__(self, params: Params) -> None:
        self.params = params

    def transcribe(self, segment: SpeechSegment) -> str:
        voice = _voice(segment)
        return voice.text or "" if voice else ""


def register() -> None:
    """Add the stand-ins to the plugin catalog under the name ``stand_in``."""
    for kind, cls in (
        (PluginKind.FACE, "FakeFaceEmbedder"),
        (PluginKind.SPEAKER, "FakeSpeakerEmbedder"),
        (PluginKind.STT, "FakeSpeechToText"),
    ):
        registry.register(
            PluginSpec(
                kind,
                STAND_IN,
                "Test stand-in (identities from the test room).",
                f"support.perception:{cls}",
            )
        )
