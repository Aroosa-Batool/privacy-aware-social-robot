"""`pasr setup` on stand-in devices (system clock: the face takes about half a second)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pasr.cli import app
from pasr.domain.enums import Biometric
from pasr.live.desktop import DesktopWindow
from pasr.orchestration.enrollment import FACE_GUIDANCE
from pasr.orchestration.offline import open_offline
from pasr.settings.loader import load_settings, read_overrides
from support.live import Windows


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stand_in_robot) -> Path:
    path = tmp_path / "data"
    monkeypatch.setenv("PASR__STORAGE__DATA_DIR", str(path))
    monkeypatch.setenv("PASR__HARDWARE__MICROPHONE__CHUNK_MS", "250")
    return path


def setup(*args: str):
    base = ["setup", "--name", "Aroosa", "--policy", "always_ask"]
    return CliRunner().invoke(app, [*base, *args])


def test_setup_saves_the_owner_and_the_answers(data_dir: Path):
    result = setup("--modality", "audio_only", "--no-enroll")
    assert result.exit_code == 0, result.output
    assert open_offline(load_settings()).repos.owner.get().display_name == "Aroosa"
    privacy = load_settings().privacy
    assert (privacy.detection_modality.value, privacy.disclosure_policy.value) == (
        "audio_only",
        "always_ask",
    )
    assert read_overrides(data_dir)["privacy"] == {"detection_modality": "audio_only"}


def test_setup_enrols_the_face_with_guidance(data_dir: Path):
    result = setup("--modality", "audio_and_camera", "--no-voice")
    assert result.exit_code == 0, result.output
    assert FACE_GUIDANCE in result.output and "face: 5 samples" in result.output
    enrolled = open_offline(load_settings()).repos.owner.enrollment()
    assert enrolled[Biometric.FACE][0] == 5 and Biometric.VOICE not in enrolled


def test_live_view_opens_a_window_for_this_run_only(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, live_windows: Windows
):
    monkeypatch.setattr(DesktopWindow, "INTERVAL_S", 0.01)
    result = setup("--modality", "audio_and_camera", "--no-voice", "--live-view")
    assert result.exit_code == 0, result.output
    assert "Live view on" in result.output
    (window,) = live_windows.opened
    assert window.views[0].title == "Enrolling the owner's face"
    assert window.closed  # with the robot
    assert "live_view" not in read_overrides(data_dir)


def test_without_live_view_no_window_opens(data_dir: Path, live_windows: Windows):
    result = setup("--modality", "audio_and_camera", "--no-voice")
    assert result.exit_code == 0, result.output
    assert live_windows.opened == []


def test_audio_only_never_enrols_the_face(data_dir: Path):
    result = setup("--modality", "audio_only", "--no-voice")
    assert result.exit_code == 0, result.output
    assert "skipping face enrolment" in result.output and "face:" not in result.output
    assert "Enrolling" not in result.output  # nothing left to enrol: the robot is not started
    assert open_offline(load_settings()).repos.owner.enrollment() == {}


def test_camera_only_never_enrols_the_voice(data_dir: Path):
    result = setup("--modality", "camera_only", "--no-face")
    assert result.exit_code == 0, result.output
    assert "skipping voice enrolment" in result.output and "voice:" not in result.output
    assert open_offline(load_settings()).repos.owner.enrollment() == {}
    assert load_settings().privacy.detection_modality.value == "camera_only"


def test_device_commands_wait_for_a_running_robot(data_dir: Path):
    from pasr.orchestration.lock import RuntimeLock

    with RuntimeLock(data_dir):  # e.g. `pasr run` in another terminal
        for command in (["hardware", "check", "--device", "camera"], ["hardware", "list"]):
            result = CliRunner().invoke(app, command)
            assert result.exit_code == 1 and "another pasr runtime" in result.output
