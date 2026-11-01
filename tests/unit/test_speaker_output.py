"""The robot's voice on a chosen output device instead of the macOS default."""

import sys
import types

import numpy as np
import pytest

from fakes import FakeSoundDevice, install_fake_ohbot
from pasr.hardware.ohbot_driver import OhbotDriver
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.speaker.output import find_output_device
from pasr.hardware.speaker.real import OhbotSpeaker


@pytest.fixture
def audio(monkeypatch):
    world = FakeSoundDevice().install(monkeypatch)
    soundfile = types.ModuleType("soundfile")
    soundfile.read = lambda path, dtype="float32": (np.zeros(2205, dtype=np.float32), 22050)
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)
    return world


def test_output_devices_match_by_name_or_prefix_and_skip_inputs(audio):
    assert find_output_device("MacBook Air Speakers") == 1
    assert find_output_device("AirPods") == 3
    with pytest.raises(HardwareNotAvailableError, match="'MacBook Air Microphone' not found"):
        find_output_device("MacBook Air Microphone")  # an input only
    with pytest.raises(HardwareNotAvailableError, match="outputs: 'MacBook Air Speakers'"):
        find_output_device("HDMI")


async def test_ohbot_voice_plays_on_the_chosen_device(monkeypatch, tmp_path, audio):
    ohbot = install_fake_ohbot(monkeypatch)
    driver = OhbotDriver("auto", tmp_path)
    speaker = OhbotSpeaker("auto", output_device="MacBook Air Speakers", driver=driver)
    await speaker.say("Reminder: dentist")
    assert ("say", "Reminder: dentist") in ohbot.calls  # lip sync still the library's
    ((data, rate, device),) = audio.played
    assert (rate, device, data.shape) == (22050, 1, (2205,))
    assert ohbot.default_played == []  # afplay (the macOS default output) not used

    await OhbotSpeaker("auto", driver=driver).say("again")  # no device: library default
    assert ohbot.default_played == ["ohbotData/ohbotspeech.wav"] and len(audio.played) == 1


async def test_unknown_device_fails_before_speaking(monkeypatch, tmp_path, audio):
    ohbot = install_fake_ohbot(monkeypatch)
    speaker = OhbotSpeaker("auto", output_device="HDMI", driver=OhbotDriver("auto", tmp_path))
    with pytest.raises(HardwareNotAvailableError, match="audio output 'HDMI' not found"):
        await speaker.say("hello")
    assert not any(call[0] == "say" for call in ohbot.calls)


async def test_missing_audio_libraries_are_named(monkeypatch, tmp_path):
    install_fake_ohbot(monkeypatch)
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    speaker = OhbotSpeaker("auto", output_device="X", driver=OhbotDriver("auto", tmp_path))
    with pytest.raises(HardwareNotAvailableError, match="needs sounddevice: uv sync"):
        await speaker.say("hello")
