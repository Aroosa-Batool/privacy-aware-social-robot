"""The real models over researcher-supplied files. Excluded by default; run with
``uv run pytest -m models`` after ``pasr models download``, with:

    PASR_TEST_WAV_OWNER / PASR_TEST_WAV_OTHER      16 kHz WAV files of two different people
    PASR_TEST_IMAGES_OWNER / PASR_TEST_IMAGES_OTHER folders of face images of two people
"""

import os
from contextlib import aclosing
from importlib.util import find_spec
from pathlib import Path

import pytest

from pasr.domain.identity import cosine
from pasr.hardware.camera.real import ImageFolderCamera
from pasr.hardware.microphone.real import WavFileMicrophone
from pasr.orchestration.clock import SystemClock
from pasr.perception import registry
from pasr.perception.registry import PluginKind
from pasr.perception.segmenter import SpeechSegmenter

pytestmark = pytest.mark.models


def env_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"set {name}")
    return Path(value)


def needs(*modules: str) -> None:
    missing = [m for m in modules if find_spec(m) is None]
    if missing:
        pytest.skip(f"not installed: {', '.join(missing)}")


async def voice_embeddings(plugin, path: Path, vad):
    clock = SystemClock()
    segmenter = SpeechSegmenter(
        speech_threshold=0.5, min_speech_ms=500, min_silence_ms=300, max_segment_seconds=5
    )
    embeddings = []
    async with aclosing(
        WavFileMicrophone(path, 16000, 32, clock=clock, realtime=False).stream()
    ) as s:
        async for chunk in s:
            for segment in segmenter.push(chunk, vad.speech_probability(chunk)):
                embeddings.append(plugin.embed(segment))
    embeddings += [plugin.embed(seg) for seg in segmenter.flush()]
    assert embeddings, f"no speech found in {path}"
    return embeddings


@pytest.mark.parametrize("name", ["speechbrain_ecapa", "resemblyzer"])
async def test_speaker_models_separate_two_people(name):
    needs("torch", "silero_vad")
    spec = registry.get_spec(PluginKind.SPEAKER, name)
    if not spec.available:
        pytest.skip(spec.status)
    plugin = registry.create(PluginKind.SPEAKER, name)
    vad = registry.create(PluginKind.VAD, "silero")
    owner = await voice_embeddings(plugin, env_path("PASR_TEST_WAV_OWNER"), vad)
    other = await voice_embeddings(plugin, env_path("PASR_TEST_WAV_OTHER"), vad)
    same = min(cosine(a, b) for a in owner for b in owner)
    different = max(cosine(a, b) for a in owner for b in other)
    assert same > different, f"{name}: owner-owner {same:.2f} vs owner-other {different:.2f}"


async def test_face_model_separates_two_people():
    needs("insightface", "onnxruntime", "cv2")
    plugin = registry.create(PluginKind.FACE, "insightface")
    clock = SystemClock()

    async def embeddings(folder: Path):
        camera = ImageFolderCamera(folder, clock=clock)
        await camera.open()
        count = len(camera._files)
        found = []
        for _ in range(count):
            faces = plugin.detect_and_embed(await camera.grab())
            if len(faces) == 1:
                found.append(faces[0].embedding)
        assert found, f"no single-face images in {folder}"
        return found

    owner = await embeddings(env_path("PASR_TEST_IMAGES_OWNER"))
    other = await embeddings(env_path("PASR_TEST_IMAGES_OTHER"))
    same = min(cosine(a, b) for a in owner for b in owner)
    different = max(cosine(a, b) for a in owner for b in other)
    assert same > different, f"owner-owner {same:.2f} vs owner-other {different:.2f}"


def test_sensitivity_model_judges_clear_reminders():
    needs("transformers", "torch")
    plugin = registry.create(PluginKind.SENSITIVITY, "zero_shot")
    for title in ("Doctor's appointment", "Take my antidepressants", "Call the debt collector"):
        assert plugin.classify(title).sensitive, title
    for title in ("Buy groceries", "Water the plants", "Drinks with friends"):
        assert not plugin.classify(title).sensitive, title
