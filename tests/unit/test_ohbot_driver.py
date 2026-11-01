import threading
from pathlib import Path

import pytest

from fakes import install_fake_ohbot
from pasr.domain.enums import Direction
from pasr.hardware.ohbot_driver import (
    HEADTURN,
    SPEECH_FILE,
    OhbotDriver,
    TurnPositions,
    sanitise_speech,
)
from pasr.hardware.protocols import HardwareNotAvailableError


def test_import_happens_inside_the_work_dir_and_init_runs_once(monkeypatch, tmp_path):
    fake = install_fake_ohbot(monkeypatch)
    driver = OhbotDriver("auto", tmp_path / "work")
    driver.ensure_started()
    driver.ensure_started()
    assert fake.import_cwd == (tmp_path / "work").resolve() == Path.cwd().resolve()
    assert fake.init_ports == []  # 'auto' relies on the library's own probe at import
    assert driver.started


def test_explicit_port_survives_the_librarys_port_indexing(monkeypatch, tmp_path):
    """ohbot.init(portName) probes portName[0]; a plain string would probe "/"."""
    port = "/dev/cu.usbmodem101"
    fake = install_fake_ohbot(monkeypatch, connected=False, answering=(port,))
    OhbotDriver(port, tmp_path).ensure_started()
    assert fake.probed == [port]
    assert fake.port == port and isinstance(fake.port, str)


def test_the_api_is_the_submodule_not_the_empty_package(monkeypatch, tmp_path):
    import sys

    install_fake_ohbot(monkeypatch)
    OhbotDriver("auto", tmp_path).ensure_started()
    assert not hasattr(sys.modules["ohbot"], "move")
    assert hasattr(sys.modules["ohbot.ohbot"], "move")


def test_missing_robot_and_missing_library_fail_clearly(monkeypatch, tmp_path):
    fake = install_fake_ohbot(monkeypatch, connected=False)  # no port answers
    with pytest.raises(HardwareNotAvailableError, match="No Ohbot found on /dev/x"):
        OhbotDriver("/dev/x", tmp_path).ensure_started()
    assert fake.probed == ["/dev/x"]

    monkeypatch.setitem(__import__("sys").modules, "ohbot", None)
    with pytest.raises(HardwareNotAvailableError, match="ohbot library is not installed: uv sync"):
        OhbotDriver("auto", tmp_path).ensure_started()


def test_calls_are_serialised_and_the_speech_file_is_removed(monkeypatch, tmp_path):
    fake = install_fake_ohbot(monkeypatch)
    driver = OhbotDriver("auto", tmp_path)
    driver.ensure_started()

    def worker() -> None:
        for _ in range(20):
            driver.move(HEADTURN, 5, 5)
            driver.say("hello")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for c in fake.calls if c[0] == "say") == 80  # no AssertionError from overlaps
    assert not (tmp_path / SPEECH_FILE).exists()

    driver.stop()
    driver.stop()
    assert fake.calls.count(("close",)) == 1
    with pytest.raises(HardwareNotAvailableError):
        driver.move(HEADTURN, 5)


def test_speech_works_after_the_cwd_or_the_work_dir_changed(monkeypatch, tmp_path):
    """The library is imported once per process but writes ohbotData/ relative to the CWD on
    every say(): a later driver (or a chdir elsewhere) must still find the folder."""
    import os

    fake = install_fake_ohbot(monkeypatch)
    first = OhbotDriver("auto", tmp_path / "first")
    first.ensure_started()
    first.stop()
    os.chdir(tmp_path)
    second = OhbotDriver("auto", tmp_path / "second")  # library already imported
    second.ensure_started()
    os.chdir(tmp_path)
    second.say("hello")
    assert ("say", "hello") in fake.calls
    assert (tmp_path / "second" / "ohbotData").is_dir()
    assert not (tmp_path / "second" / SPEECH_FILE).exists()


def test_shared_driver_is_one_per_process(monkeypatch, tmp_path):
    assert OhbotDriver.shared("auto") is OhbotDriver.shared("auto")


def test_turn_positions_and_speech_sanitising():
    turns = TurnPositions(2, 5, 8)
    assert [turns.for_direction(d) for d in Direction] == [2, 5, 8]
    assert (
        sanitise_speech("Doctor's visit; rm -rf $HOME `x`\n at 2pm")
        == "Doctor s visit rm -rf HOME x at 2pm"
    )
