"""`pasr calibrate` on stand-in devices (system clock)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pasr.cli import app
from pasr.settings.loader import read_overrides


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stand_in_robot) -> Path:
    path = tmp_path / "data"
    monkeypatch.setenv("PASR__STORAGE__DATA_DIR", str(path))
    monkeypatch.setenv("PASR__HARDWARE__MICROPHONE__CHUNK_MS", "250")
    return path


def test_calibrate_needs_an_enrolment_then_saves_the_threshold(data_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["calibrate", "face", "--others", "0"], input="\n")
    assert result.exit_code == 1 and "enrol the owner's face first" in result.output

    setup = runner.invoke(
        app,
        [
            "setup",
            "--name",
            "A",
            "--modality",
            "audio_and_camera",
            "--policy",
            "always_ask",
            "--no-voice",
        ],
    )
    assert setup.exit_code == 0, setup.output

    result = runner.invoke(app, ["calibrate", "face", "--others", "0", "--apply"], input="\n")
    assert result.exit_code == 0, result.output
    assert "Owner: press Enter, then look at the camera" in result.output
    assert "suggested identity.face_threshold" in result.output
    assert "no samples of other people" in result.output
    assert "Saved identity.face_threshold" in result.output
    assert -1 < read_overrides(data_dir)["identity"]["face_threshold"] < 1


def test_file_sources_must_match_the_modality(data_dir: Path):
    result = CliRunner().invoke(app, ["calibrate", "face", "--wav", "x.wav"])
    assert result.exit_code == 1 and "--images with 'face'" in result.output
