from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import cast

from pasr.perception import registry
from pasr.perception.protocols import (
    DateTimeParser,
    FaceEmbedder,
    SensitivityClassifier,
    SpeakerEmbedder,
    SpeechToText,
    VoiceActivityDetector,
)
from pasr.perception.registry import PluginKind
from pasr.settings.schema import PerceptionSettings


class PerceptionBundle:
    """The configured plugins, created lazily: with audio-only detection the face model is never
    loaded, and the camera pipeline never exists."""

    def __init__(self, settings: PerceptionSettings, *, models_dir: Path | None = None) -> None:
        self.settings = settings
        self.models_dir = models_dir

    def _create(self, kind: PluginKind) -> object:
        choice = self.settings.choice(kind)
        params = dict(choice.params)
        cls = registry.load_class(registry.get_spec(kind, choice.plugin))
        # Plugins that download weights declare ``models_dir`` in their Params; the configured
        # storage.models_dir wins over the Params default unless the user set it per plugin.
        if self.models_dir is not None and "models_dir" in cls.Params.model_fields:
            params.setdefault("models_dir", str(self.models_dir))
        return registry.create(kind, choice.plugin, params)

    def plugin_name(self, kind: PluginKind) -> str:
        return self.settings.choice(kind).plugin

    @cached_property
    def face(self) -> FaceEmbedder:
        return cast(FaceEmbedder, self._create(PluginKind.FACE))

    @cached_property
    def speaker(self) -> SpeakerEmbedder:
        return cast(SpeakerEmbedder, self._create(PluginKind.SPEAKER))

    @cached_property
    def vad(self) -> VoiceActivityDetector:
        return cast(VoiceActivityDetector, self._create(PluginKind.VAD))

    @cached_property
    def stt(self) -> SpeechToText:
        return cast(SpeechToText, self._create(PluginKind.STT))

    @cached_property
    def sensitivity(self) -> SensitivityClassifier:
        return cast(SensitivityClassifier, self._create(PluginKind.SENSITIVITY))

    @cached_property
    def datetime_parser(self) -> DateTimeParser:
        return cast(DateTimeParser, self._create(PluginKind.DATETIME_PARSER))
