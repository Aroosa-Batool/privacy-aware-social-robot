"""Catalog of perception plugins.

The catalog is declarative so that listing plugins (e.g. in the dashboard) never imports heavy
ML libraries. A plugin class is imported only when it is created. A spec without a target is a
planned plugin, listed with the milestone that will deliver it.

A plugin class has a nested pydantic ``Params`` model (fields declared with
``pasr.settings.tiers.setting``) and is constructed as ``PluginClass(params)``.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.util import find_spec
from typing import Any

from pydantic import BaseModel


class PluginKind(StrEnum):
    FACE = "face"
    SPEAKER = "speaker"
    VAD = "vad"
    STT = "stt"
    SENSITIVITY = "sensitivity"
    DATETIME_PARSER = "datetime_parser"


class UnknownPluginError(LookupError):
    pass


class PluginUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PluginSpec:
    kind: PluginKind
    name: str
    description: str
    target: str | None
    """``"package.module:ClassName"``; ``None`` for plugins that are planned but not built yet."""
    requires: tuple[str, ...] = ()
    milestone: str | None = None

    @property
    def missing_dependencies(self) -> list[str]:
        return [module for module in self.requires if not _installed(module)]

    @property
    def available(self) -> bool:
        return self.target is not None and not self.missing_dependencies

    @property
    def status(self) -> str:
        if self.target is None:
            return f"planned ({self.milestone})" if self.milestone else "planned"
        if missing := self.missing_dependencies:
            return "missing " + ", ".join(missing)
        return "available"


def _installed(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except ValueError:  # already imported, but without a spec (e.g. a stub module)
        return True


_CATALOG: list[PluginSpec] = [
    PluginSpec(
        PluginKind.FACE,
        "insightface",
        "InsightFace buffalo_l (SCRFD detector + ArcFace) on onnxruntime. "
        "Model weights are licensed for non-commercial research only.",
        "pasr.perception.face.insightface:InsightFaceEmbedder",
        ("insightface", "onnxruntime", "cv2"),
    ),
    PluginSpec(
        PluginKind.SPEAKER,
        "resemblyzer",
        "Resemblyzer d-vector (MIT). Light; weights ship with the package.",
        "pasr.perception.speaker.resemblyzer:ResemblyzerEmbedder",
        ("resemblyzer", "torch"),
    ),
    PluginSpec(
        PluginKind.SPEAKER,
        "speechbrain_ecapa",
        "SpeechBrain ECAPA-TDNN speaker verification model (needs torch).",
        "pasr.perception.speaker.speechbrain_ecapa:SpeechBrainEcapaEmbedder",
        ("speechbrain", "torch", "torchaudio"),
    ),
    PluginSpec(
        PluginKind.VAD,
        "energy",
        "RMS energy threshold. No model; works in quiet rooms.",
        "pasr.perception.vad.energy:EnergyVAD",
    ),
    PluginSpec(
        PluginKind.VAD,
        "silero",
        "Silero VAD neural voice-activity detector (MIT, needs torch).",
        "pasr.perception.vad.silero:SileroVAD",
        ("silero_vad", "torch"),
    ),
    PluginSpec(
        PluginKind.STT,
        "faster_whisper",
        "faster-whisper: local Whisper on CTranslate2 (MIT; weights downloaded once).",
        "pasr.perception.stt.faster_whisper:FasterWhisperSpeechToText",
        ("faster_whisper",),
    ),
    PluginSpec(
        PluginKind.SENSITIVITY,
        "zero_shot",
        "Zero-shot DeBERTa-v3 model (MIT): is the reminder about a sensitive topic such as "
        "health or money? Runs locally; weights downloaded once.",
        "pasr.perception.sensitivity.zero_shot:ZeroShotSensitivityClassifier",
        ("transformers", "torch"),
    ),
    PluginSpec(
        PluginKind.SENSITIVITY,
        "keyword",
        "Keyword lists: e.g. 'doctor' is sensitive, 'groceries' is not.",
        "pasr.perception.sensitivity.keyword:KeywordSensitivityClassifier",
    ),
    PluginSpec(
        PluginKind.DATETIME_PARSER,
        "dateparser",
        "Regex time extraction + the dateparser library for dates.",
        "pasr.perception.datetime_parse.dateparser_plugin:DateparserDateTimeParser",
        ("dateparser",),
    ),
]


def register(spec: PluginSpec) -> None:
    """Add a plugin (e.g. from a researcher's own package). Replaces a spec with the same name."""
    _CATALOG[:] = [s for s in _CATALOG if (s.kind, s.name) != (spec.kind, spec.name)]
    _CATALOG.append(spec)


def specs(kind: PluginKind | None = None) -> list[PluginSpec]:
    return [s for s in _CATALOG if kind is None or s.kind is kind]


def get_spec(kind: PluginKind, name: str) -> PluginSpec:
    for spec in _CATALOG:
        if spec.kind is kind and spec.name == name:
            return spec
    known = ", ".join(s.name for s in specs(kind))
    raise UnknownPluginError(f"unknown {kind} plugin {name!r} (known: {known})")


def load_class(spec: PluginSpec) -> type[Any]:
    if spec.target is None:
        raise PluginUnavailableError(f"{spec.kind} plugin {spec.name!r} is {spec.status}")
    if missing := spec.missing_dependencies:
        raise PluginUnavailableError(
            f"{spec.kind} plugin {spec.name!r} needs: {', '.join(missing)}"
        )
    module_name, _, class_name = spec.target.partition(":")
    cls: type[Any] = getattr(importlib.import_module(module_name), class_name)
    return cls


def params_model(kind: PluginKind, name: str) -> type[BaseModel] | None:
    spec = get_spec(kind, name)
    if not spec.available:
        return None
    params: type[BaseModel] = load_class(spec).Params
    return params


def create(kind: PluginKind, name: str, params: Mapping[str, Any] | None = None) -> Any:
    cls = load_class(get_spec(kind, name))
    return cls(cls.Params.model_validate(dict(params or {})))


def recommended_threshold(kind: PluginKind, name: str) -> float | None:
    """A plugin's suggested starting similarity threshold (``recommended_threshold`` class
    attribute), or ``None`` when it declares none or is not installed. Cheap: plugin modules
    import their ML libraries lazily."""
    spec = get_spec(kind, name)
    if not spec.available:
        return None
    value = getattr(load_class(spec), "recommended_threshold", None)
    return None if value is None else float(value)
