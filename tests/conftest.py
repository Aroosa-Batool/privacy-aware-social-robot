from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from fakes import FakeCameraHelpers
from pasr.hardware.camera import helper
from pasr.orchestration.runtime import Runtime
from pasr.settings import loader
from pasr.settings.loader import deep_merge
from pasr.settings.schema import Settings
from pasr.storage.db import Database
from pasr.storage.repos import Repositories
from support import perception as stand_in_perception
from support.clock import VirtualClock
from support.devices import stand_in_hardware
from support.live import Windows
from support.perception import STAND_IN_PERCEPTION
from support.room import Room

stand_in_perception.register()
os.environ["HF_HUB_OFFLINE"] = "1"  # a test that loads a real model by mistake fails, offline

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests never see the developer's PASR__ variables or .env file."""
    for key in list(os.environ):
        if key.upper().startswith("PASR__"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(loader, "ENV_FILE", tmp_path / ".env")


@pytest.fixture(autouse=True)
def live_windows(monkeypatch: pytest.MonkeyPatch) -> Windows:
    """Tests never open a real live-view window: runtimes that show one (the dashboard's, the
    CLI's) get recording stand-ins, listed here."""
    windows = Windows()
    monkeypatch.setattr("pasr.live.desktop.WindowProcess", windows)
    return windows


@pytest.fixture(autouse=True)
def camera_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> FakeCameraHelpers:
    """Tests never open a real camera: camera helper processes run with a stand-in cv2. Their
    plan lives in a folder of its own, away from the data folders tests check."""
    helpers = FakeCameraHelpers(tmp_path_factory.mktemp("camera"))
    monkeypatch.setattr(helper, "COMMAND", helpers.command)
    return helpers


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def make(**overrides: Any) -> Settings:
        base = {
            "storage": {"data_dir": str(tmp_path / "data")},
            "hardware": {"microphone": {"chunk_ms": 250}},
            "perception": STAND_IN_PERCEPTION,
        }
        return Settings.model_validate(deep_merge(base, overrides))

    return make


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


@pytest.fixture
def clock() -> VirtualClock:
    return VirtualClock(T0)


@pytest.fixture
def repos(tmp_path: Path) -> Repositories:
    db = Database.in_dir(tmp_path / "db")
    db.migrate()
    return Repositories(db)


def stand_ins(settings: Settings, clock: Any) -> Any:
    mic = settings.hardware.microphone
    return stand_in_hardware(Room(clock), clock, sample_rate=mic.sample_rate, chunk_ms=mic.chunk_ms)


@pytest.fixture
def runtime(settings: Settings, clock: VirtualClock) -> Iterator[Runtime]:
    """A runtime on stand-in devices and virtual time; the room is ``runtime.hardware.room``."""
    yield Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        inline_compute=True,
        session_id="test",
    )


@pytest.fixture
def stand_in_robot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtimes built from saved settings (CLI commands, the dashboard) get stand-in devices on
    the system clock and stand-in perception, instead of the robot."""

    def build(hardware: Any, *, clock: Any, on_watch_address: Any = None) -> Any:
        mic = hardware.microphone
        return stand_in_hardware(
            Room(clock), clock, sample_rate=mic.sample_rate, chunk_ms=mic.chunk_ms
        )

    monkeypatch.setattr("pasr.orchestration.runtime.build_hardware", build)
    monkeypatch.setattr("pasr.hardware.check.build_hardware", build)
    for kind, choice in STAND_IN_PERCEPTION.items():
        monkeypatch.setenv(f"PASR__PERCEPTION__{kind.upper()}__PLUGIN", choice["plugin"])


@pytest.fixture(autouse=True)
def isolated_ohbot_driver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """The Ohbot driver is process-global and changes the working directory: give every test a
    fresh driver with a temporary work dir, and restore the CWD afterwards."""
    from pasr.hardware import ohbot_driver

    cwd = os.getcwd()
    monkeypatch.setattr(ohbot_driver, "OHBOT_WORK_DIR", tmp_path / ".ohbot")
    monkeypatch.setattr(ohbot_driver.OhbotDriver, "_shared", None)
    try:
        yield
    finally:
        ohbot_driver.OhbotDriver._shared = None
        os.chdir(cwd)
