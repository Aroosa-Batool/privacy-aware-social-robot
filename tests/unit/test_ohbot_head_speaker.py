import asyncio

import pytest

from fakes import install_fake_ohbot
from pasr.domain.enums import Direction, Pose
from pasr.hardware.head.real import OhbotHead
from pasr.hardware.ohbot_driver import (
    HEADNOD,
    HEADTURN,
    LIDBLINK,
    POSES,
    OhbotDriver,
    TurnPositions,
)
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.speaker.real import MacSaySpeaker, OhbotSpeaker


@pytest.fixture
def head(monkeypatch, tmp_path):
    fake = install_fake_ohbot(monkeypatch)
    driver = OhbotDriver("auto", tmp_path)
    head = OhbotHead("auto", turns=TurnPositions(2, 5, 8), move_seconds=0.0, driver=driver)
    return fake, head


async def test_head_looks_poses_blinks_and_rests_on_close(head):
    fake, head = head
    await head.connect()
    assert fake.calls[-1] == ("move", HEADTURN, 5.0, 5)
    for direction, position in [(Direction.LEFT, 2.0), (Direction.RIGHT, 8.0)]:
        await head.look(direction, speed=7)
        assert fake.calls[-1] == ("move", HEADTURN, position, 7)
    await head.pose(Pose.ATTENTION)
    moved = {c[1]: c[2] for c in fake.calls if c[0] == "move"}
    assert all(moved[m] == p for m, p in POSES[Pose.ATTENTION].items())
    fake.calls.clear()
    await head.blink()
    assert [c[:3] for c in fake.calls] == [("move", LIDBLINK, 0.0), ("move", LIDBLINK, 10.0)]
    await head.close()
    assert fake.calls[-1] == ("close",)
    await head.close()  # idempotent


async def test_nudge_turns_and_nods_from_where_the_head_points(head):
    fake, head = head
    await head.connect()
    await head.pose(Pose.ATTENTION)
    nod = POSES[Pose.ATTENTION][HEADNOD]
    fake.calls.clear()
    assert await head.nudge(-1.5, 0.5, speed=6) == (-1.5, 0.5)
    assert fake.calls == [("move", HEADTURN, 3.5, 6), ("move", HEADNOD, nod + 0.5, 6)]
    fake.calls.clear()
    assert await head.nudge(0.0, -0.5) == (0.0, -0.5)  # only the nod motor moves
    assert fake.calls == [("move", HEADNOD, float(nod), 5)]
    fake.calls.clear()
    assert await head.nudge(-9.0, 0.0) == (-3.5, 0.0)  # stops at the motor's end
    assert fake.calls == [("move", HEADTURN, 0.0, 5)]
    fake.calls.clear()
    assert await head.nudge(-1.0, 0.0) == (0.0, 0.0)  # already there: nothing to move
    assert fake.calls == []
    await head.look(Direction.FRONT)
    assert fake.calls[-1] == ("move", HEADTURN, 5.0, 5)


async def test_speaker_starts_the_driver_itself(monkeypatch, tmp_path):
    fake = install_fake_ohbot(monkeypatch)
    speaker = OhbotSpeaker("auto", driver=OhbotDriver("auto", tmp_path))
    await speaker.say("Reminder: dentist")
    assert ("say", "Reminder: dentist") in fake.calls


async def test_mac_say_uses_argv_not_a_shell(monkeypatch):
    calls = []

    class Process:
        returncode = 0

        async def wait(self):
            return self.returncode

    async def fake_exec(*args):
        calls.append(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await MacSaySpeaker("Samantha").say("-dash first; $HOME")
    assert calls == [("say", "-v", "Samantha", " -dash first; $HOME")]
    await MacSaySpeaker(output_device="MacBook Air Speakers").say("hi")
    assert calls[-1] == ("say", "-a", "MacBook Air Speakers", "hi")

    async def missing(*args):
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing)
    with pytest.raises(HardwareNotAvailableError):
        await MacSaySpeaker().say("hi")
