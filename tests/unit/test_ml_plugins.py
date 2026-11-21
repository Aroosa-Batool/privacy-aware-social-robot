"""The ML plugins against fake libraries: lazy loading, embedding shape and model names, and
the Silero windowing/state rules. The real models run in tests/models (``-m models``)."""

from datetime import timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import T0
from fakes import FakeML
from pasr.domain.media import AudioChunk, Frame, SpeechSegment
from pasr.perception import registry
from pasr.perception.face.insightface import InsightFaceEmbedder
from pasr.perception.registry import PluginKind, PluginUnavailableError
from pasr.perception.sensitivity.zero_shot import DEFAULT_TOPICS, ZeroShotSensitivityClassifier
from pasr.perception.speaker.resemblyzer import ResemblyzerEmbedder
from pasr.perception.speaker.speechbrain_ecapa import SpeechBrainEcapaEmbedder
from pasr.perception.stt.faster_whisper import FasterWhisperSpeechToText
from pasr.perception.vad.silero import SileroVAD


def frame() -> Frame:
    return Frame(image=np.zeros((480, 640, 3), dtype=np.uint8), captured_at=T0)


def segment(seconds: float = 1.0, rate: int = 16000, level: float = 0.1) -> SpeechSegment:
    samples = (np.random.default_rng(1).standard_normal(int(seconds * rate)) * level).astype(
        np.float32
    )
    return SpeechSegment(samples, rate, T0, T0 + timedelta(seconds=seconds))


def chunk(start: object, n: int = 512, rate: int = 16000, level: float = 0.1) -> AudioChunk:
    samples = (np.random.default_rng(2).standard_normal(n) * level).astype(np.float32)
    return AudioChunk(samples, rate, start)  # type: ignore[arg-type]


def test_construction_touches_no_library(monkeypatch):
    ml = FakeML().install(monkeypatch)
    plugins = [
        registry.create(PluginKind.FACE, "insightface"),
        registry.create(PluginKind.SPEAKER, "speechbrain_ecapa"),
        registry.create(PluginKind.SPEAKER, "resemblyzer"),
        registry.create(PluginKind.VAD, "silero"),
        registry.create(PluginKind.STT, "faster_whisper"),
        registry.create(PluginKind.SENSITIVITY, "zero_shot"),
    ]
    assert ml.events == [] and ml.threads == []
    assert [p.model for p in plugins[:3]] == [
        "insightface-buffalo_l",
        "speechbrain-spkrec-ecapa-voxceleb",
        "resemblyzer-dvector",
    ]
    for spec in registry.specs():
        if spec.name in (
            "insightface",
            "speechbrain_ecapa",
            "resemblyzer",
            "silero",
            "faster_whisper",
            "zero_shot",
        ):
            assert spec.status == "available"


def test_insightface_loads_only_detection_and_recognition(monkeypatch, tmp_path):
    geometry = {
        "bbox": np.array([10, 20, 110, 140], np.float32),
        "kps": np.array([[40, 60], [80, 60], [60, 90], [45, 110], [75, 110]], np.float32),
    }
    faces = [(0.9, np.ones(512), geometry), (0.3, np.ones(512)), (0.8, np.zeros(512) + 2)]
    ml = FakeML(faces=faces).install(monkeypatch)
    params = InsightFaceEmbedder.Params(models_dir=tmp_path, det_size=320, min_det_score=0.5)
    plugin = InsightFaceEmbedder(params)
    faces = plugin.detect_and_embed(frame())
    (_, init), (_, prepare) = ml.events[:2]
    assert init["name"] == "buffalo_l" and init["root"] == str(tmp_path / "insightface")
    assert init["allowed_modules"] == ["detection", "recognition"]
    assert init["providers"] == ["CPUExecutionProvider"]
    assert prepare == {"ctx_id": 0, "det_thresh": 0.5, "det_size": (320, 320)}
    assert [round(f.score, 1) for f in faces] == [0.9, 0.8]  # the 0.3 detection is dropped
    assert all(
        f.embedding.dim == 512 and f.embedding.model == "insightface-buffalo_l" for f in faces
    )
    assert np.isclose(np.linalg.norm(faces[0].embedding.vector), 1.0)
    assert faces[0].box == (10.0, 20.0, 110.0, 140.0)
    assert faces[0].landmarks == (
        (40.0, 60.0),
        (80.0, 60.0),
        (60.0, 90.0),
        (45.0, 110.0),
        (75.0, 110.0),
    )
    assert faces[1].box is None and faces[1].landmarks is None
    plugin.detect_and_embed(frame())
    assert sum(1 for e in ml.events if e[0] == "FaceAnalysis") == 1  # loaded once


def test_ecapa_resamples_and_names_the_model(monkeypatch, tmp_path):
    ml = FakeML().install(monkeypatch)
    plugin = SpeechBrainEcapaEmbedder(
        SpeechBrainEcapaEmbedder.Params(models_dir=tmp_path, threads=3)
    )
    embedding = plugin.embed(segment(rate=16000))
    assert embedding.dim == 192 and embedding.model == "speechbrain-spkrec-ecapa-voxceleb"
    assert ml.threads == [3]
    (_, hparams) = next(e for e in ml.events if e[0] == "from_hparams")
    assert hparams["savedir"] == str(tmp_path / "speechbrain" / "spkrec-ecapa-voxceleb")
    assert hparams["run_opts"] == {"device": "cpu"}
    assert ("resample", 8000, 16000) not in ml.events
    plugin.embed(segment(rate=8000))
    assert ("resample", 8000, 16000) in ml.events
    assert ml.events[-1] == ("encode_batch", (1, 16000))


def test_resemblyzer_falls_back_to_raw_audio_when_trimming_leaves_too_little(monkeypatch):
    ml = FakeML().install(monkeypatch)
    plugin = ResemblyzerEmbedder(ResemblyzerEmbedder.Params(min_trimmed_seconds=0.4))
    assert plugin.embed(segment(seconds=2.0)).dim == 256  # trimmed to 1.0 s: fine
    assert ml.events[-1] == ("embed_utterance", 16000)
    plugin.embed(segment(seconds=0.5))  # trimmed to 0.25 s: raw 0.5 s used instead
    assert ml.events[-1] == ("embed_utterance", 8000)
    assert plugin.embed(segment()).model == "resemblyzer-dvector"


def test_silero_windows_padding_and_state_resets(monkeypatch):
    ml = FakeML().install(monkeypatch)
    vad = SileroVAD(SileroVAD.Params())
    first = chunk(T0)
    assert 0.0 < vad.speech_probability(first) <= 1.0
    assert ml.resets == 1 and ml.events[0] == ("load_silero_vad", False)
    cursor = first.end
    for n in (512, 512 * 4, 4000):  # contiguous chunks keep the state; 4000 pads the tail
        following = chunk(cursor, n=n)
        assert vad.speech_probability(following) > 0
        cursor = following.end
    assert ml.resets == 1
    assert vad.speech_probability(chunk(cursor, n=0)) == 0.0
    assert vad.speech_probability(chunk(cursor, n=512, level=0.0)) == 0.0
    assert ml.resets == 1
    vad.speech_probability(chunk(cursor + timedelta(seconds=5)))  # a gap: new session
    assert ml.resets == 2
    with pytest.raises(ValueError, match="8000 or 16000"):
        vad.speech_probability(chunk(T0, n=512, rate=44100))
    assert vad.speech_probability(chunk(T0, n=256, rate=8000)) >= 0  # rate change resets
    assert ml.resets == 3


def test_missing_library_is_reported_with_the_extra(monkeypatch):
    FakeML(missing=("torch",)).install(monkeypatch)
    with pytest.raises(PluginUnavailableError, match="cannot load its library .*run: uv sync"):
        SileroVAD(SileroVAD.Params()).warm_up()
    FakeML(missing=("insightface",)).install(monkeypatch)
    with pytest.raises(PluginUnavailableError, match="cannot load its library .*run: uv sync"):
        InsightFaceEmbedder(InsightFaceEmbedder.Params()).warm_up()
    FakeML(missing=("transformers",)).install(monkeypatch)
    with pytest.raises(PluginUnavailableError, match="cannot load its library .*run: uv sync"):
        ZeroShotSensitivityClassifier(ZeroShotSensitivityClassifier.Params()).warm_up()


def test_recommended_thresholds(monkeypatch):
    FakeML().install(monkeypatch)
    assert registry.recommended_threshold(PluginKind.FACE, "insightface") == 0.40
    assert registry.recommended_threshold(PluginKind.SPEAKER, "speechbrain_ecapa") == 0.35
    assert registry.recommended_threshold(PluginKind.SPEAKER, "resemblyzer") == 0.75
    assert registry.recommended_threshold(PluginKind.VAD, "silero") is None
    FakeML(missing=("insightface",)).install(monkeypatch)
    assert registry.recommended_threshold(PluginKind.FACE, "insightface") is None


def test_faster_whisper_runs_locally_on_16_khz_audio(monkeypatch, tmp_path):
    ml = FakeML().install(monkeypatch)
    params = FasterWhisperSpeechToText.Params(
        models_dir=tmp_path, model_size="small", language="de", beam_size=2, threads=3
    )
    plugin = FasterWhisperSpeechToText(params)
    assert ml.events == []  # nothing loaded until the first transcript
    assert plugin.transcribe(segment()) == "doctor at two"
    (_, init) = ml.events[0]
    assert init == {
        "size": "small",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 3,
        "download_root": str(tmp_path / "faster-whisper"),
    }
    assert ml.events[-1] == ("transcribe", np.float32, 16000, {"language": "de", "beam_size": 2})
    plugin.transcribe(segment(rate=8000))  # resampled to the model's 16 kHz
    assert ml.events[-1][2] == 16000
    assert sum(1 for e in ml.events if e[0] == "WhisperModel") == 1

    auto = FasterWhisperSpeechToText(FasterWhisperSpeechToText.Params(language=None))
    auto.transcribe(segment())
    assert ml.events[-1][3]["language"] is None  # detect the language


def test_zero_shot_sensitivity_downloads_once_then_judges_topics(monkeypatch, tmp_path):
    ml = FakeML().install(monkeypatch)
    params = ZeroShotSensitivityClassifier.Params(models_dir=tmp_path, threads=3)
    plugin = ZeroShotSensitivityClassifier(params)
    assert ml.events == []  # nothing loaded until the first reminder

    result = plugin.classify("Collect the prescription from the pharmacy")
    assert result.sensitive and result.score > 0.99
    assert result.reasons == ("medication or a prescription",)
    assert ml.events[-1] == ("infer", len(DEFAULT_TOPICS))  # one batch: every topic at once
    assert ml.threads == [3]
    cache, model = str(tmp_path / "transformers"), params.model
    assert [e for e in ml.events if e[0] != "infer"] == [
        ("tokenizer", model, cache, True),  # the local copy first ...
        ("tokenizer", model, cache, False),  # ... and the one-time download when it is missing
        ("model", model, cache, False),
    ]

    groceries = plugin.classify("Buy groceries")
    assert not groceries.sensitive and groceries.score < 0.01 and groceries.reasons == ()

    ml.events.clear()
    ZeroShotSensitivityClassifier(params).warm_up()
    assert [e[3] for e in ml.events] == [True, True]  # downloaded: loaded offline from now on


def test_zero_shot_sensitivity_settings(monkeypatch, tmp_path):
    FakeML().install(monkeypatch)
    strict = ZeroShotSensitivityClassifier.Params(models_dir=tmp_path, threshold=1.0)
    assert not ZeroShotSensitivityClassifier(strict).classify("Pay the bank loan").sensitive
    own = ZeroShotSensitivityClassifier(
        ZeroShotSensitivityClassifier.Params(models_dir=tmp_path, sensitive_topics=["football"])
    )
    assert own.classify("Football on Sunday").reasons == ("football",)
    assert own.classify("   ").score == 0.0
    with pytest.raises(ValidationError):
        ZeroShotSensitivityClassifier.Params(template="no place for the topic")
