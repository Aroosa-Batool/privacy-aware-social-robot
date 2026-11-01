"""Interfaces every perception plugin implements. Plugins are synchronous pure compute; the
runtime runs them off the event loop when real hardware is used."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Protocol

from pasr.domain.media import AudioChunk, Frame, SpeechSegment
from pasr.domain.models import Embedding


@dataclass(frozen=True, slots=True)
class FaceObservation:
    embedding: Embedding
    score: float
    """Detector confidence in [0, 1]."""
    box: tuple[float, float, float, float] | None = None
    """(x1, y1, x2, y2) in pixels, for the live view and for following the face with the head;
    never stored."""
    landmarks: tuple[tuple[float, float], ...] | None = None
    """Eyes, nose tip and mouth corners in pixels, in that order, if the plugin finds them; only
    used to tell whether the face is turned away, never stored."""


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    sensitive: bool
    score: float
    """Confidence that the text is sensitive, in [0, 1]."""
    reasons: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class ParsedDateTime:
    title: str
    date: date | None
    time: time | None


class FaceEmbedder(Protocol):
    def detect_and_embed(self, frame: Frame) -> list[FaceObservation]: ...


class SpeakerEmbedder(Protocol):
    def embed(self, segment: SpeechSegment) -> Embedding: ...


class VoiceActivityDetector(Protocol):
    def speech_probability(self, chunk: AudioChunk) -> float: ...


class SpeechToText(Protocol):
    def transcribe(self, segment: SpeechSegment) -> str: ...


class SensitivityClassifier(Protocol):
    def classify(self, text: str) -> SensitivityResult: ...


class DateTimeParser(Protocol):
    def parse(self, text: str, now: datetime) -> ParsedDateTime: ...
