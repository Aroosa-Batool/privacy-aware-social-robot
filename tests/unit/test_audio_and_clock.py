import asyncio
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from pasr.domain.media import AudioChunk
from pasr.orchestration.clock import SystemClock
from pasr.perception.segmenter import SpeechSegmenter
from pasr.perception.vad.energy import EnergyVAD
from support.clock import VirtualClock, VirtualClockStalledError, with_timeout

T0 = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
SR = 16000


def chunk(index: int, *, loud: bool, ms: int = 100) -> AudioChunk:
    level = 0.15 if loud else 0.001
    samples = (np.random.default_rng(index).standard_normal(SR * ms // 1000) * level).astype(
        np.float32
    )
    return AudioChunk(samples, SR, T0 + timedelta(milliseconds=index * ms))


def segment(pattern: str, **kwargs):
    """``pattern``: one character per 100 ms chunk, ``#`` speech and ``.`` silence."""
    vad = EnergyVAD(EnergyVAD.Params())
    segmenter = SpeechSegmenter(
        speech_threshold=0.5,
        min_speech_ms=kwargs.get("min_speech_ms", 250),
        min_silence_ms=300,
        max_segment_seconds=kwargs.get("max_segment_seconds", 10),
    )
    out = []
    for i, c in enumerate(pattern):
        piece = chunk(i, loud=c == "#")
        out += segmenter.push(piece, vad.speech_probability(piece))
    return out + segmenter.flush()


def test_energy_vad_separates_speech_from_room_noise():
    vad = EnergyVAD(EnergyVAD.Params())
    assert vad.speech_probability(chunk(0, loud=True)) > 0.99
    assert vad.speech_probability(chunk(0, loud=False)) < 0.01


def test_segmenter_finds_utterances():
    segments = segment("..#####....###....")
    assert [round(s.duration_s, 1) for s in segments] == [0.5, 0.3]
    assert segments[0].start == T0 + timedelta(milliseconds=200)


def test_short_pauses_do_not_split_and_short_bursts_are_dropped():
    assert len(segment("###..###....")) == 1  # 200 ms pause < 300 ms min silence
    assert segment("..#....") == []  # 100 ms burst < 250 ms min speech


def test_long_speech_is_split():
    segments = segment("#" * 25, max_segment_seconds=1.0)
    assert [round(s.duration_s, 1) for s in segments] == [1.0, 1.0, 0.5]


async def test_virtual_clock_orders_sleepers():
    clock = VirtualClock(T0)
    order = []

    async def sleeper(name, seconds):
        await clock.sleep(seconds)
        order.append((name, clock.now() - T0))

    async def main():
        await asyncio.gather(sleeper("b", 300), sleeper("a", 60), sleeper("c", 3600))

    await clock.drive(main())
    assert order == [
        ("a", timedelta(minutes=1)),
        ("b", timedelta(minutes=5)),
        ("c", timedelta(hours=1)),
    ]


async def test_virtual_clock_detects_a_stalled_simulation():
    clock = VirtualClock(T0, stall_grace_seconds=0.05)
    with pytest.raises(VirtualClockStalledError):
        await clock.drive(asyncio.Event().wait())


async def test_virtual_clock_waits_for_work_in_a_thread():
    # A device reading a file in a thread (asyncio.to_thread) can take longer than the settle
    # iterations on a slow CI machine; that is not a stall.
    clock = VirtualClock(T0)

    async def flow():
        await asyncio.to_thread(time.sleep, 0.05)
        await clock.sleep(60)
        return clock.now() - T0

    assert await clock.drive(flow()) == timedelta(minutes=1)


async def test_with_timeout():
    clock = VirtualClock(T0)

    async def slow():
        await clock.sleep(10)
        return "done"

    assert await clock.drive(with_timeout(clock, slow(), 5)) is None
    assert await clock.drive(with_timeout(clock, slow(), 50)) == "done"


async def test_system_clock_sleeps_until_a_time():
    clock = SystemClock()
    target = clock.now() + timedelta(milliseconds=30)
    await asyncio.wait_for(clock.sleep_until(target), timeout=1)
    assert clock.now() >= target
    await clock.sleep_until(target)  # in the past: returns at once
