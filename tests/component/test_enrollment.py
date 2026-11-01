"""Enrolment progress and failure messages, in simulation on the virtual clock."""

import pytest

from pasr.domain.enums import Biometric, Direction
from pasr.orchestration.enrollment import EnrollmentError, EnrollProgress
from pasr.orchestration.runtime import Runtime
from support.clock import VirtualClock
from support.room import OWNER_TAG


async def drive(runtime: Runtime, body):
    clock = runtime.clock
    assert isinstance(clock, VirtualClock)

    async def main():
        await runtime.start(run_apps=False)
        try:
            return await body()
        finally:
            await runtime.stop()

    return await clock.drive(main())


async def test_face_progress_counts_frames(runtime: Runtime):
    seen: list[EnrollProgress] = []

    async def body():
        runtime.enrollment.register("Owner")
        assert await runtime.enrollment.enroll_face(progress=seen.append) == 5

    await drive(runtime, body)
    assert [p.collected for p in seen] == [1, 2, 3, 4, 5]
    assert all(p.modality is Biometric.FACE and p.wanted == 5 for p in seen)
    assert seen[-1].frames == 5 and seen[-1].no_face == 0 and seen[-1].many_faces == 0
    assert seen[-1].elapsed_s > seen[0].elapsed_s >= 0
    assert runtime.hardware.room.camera_on is False


async def test_face_messages_distinguish_no_face_from_a_crowd(runtime: Runtime):
    async def body():
        runtime.enrollment.register("Owner")
        runtime.hardware.room.set_faces(Direction.FRONT, [])
        with pytest.raises(EnrollmentError, match="saw no face in .* frames: check"):
            await runtime.enrollment.enroll_face()
        runtime.hardware.room.set_faces(Direction.FRONT, [OWNER_TAG, "friend"])
        with pytest.raises(EnrollmentError, match="exactly one face in only 0 of"):
            await runtime.enrollment.enroll_face()

    await drive(runtime, body)


async def test_voice_progress_and_timeout_message(runtime: Runtime):
    seen: list[EnrollProgress] = []

    async def body():
        runtime.enrollment.register("Owner")
        with pytest.raises(EnrollmentError, match="heard only 0 of 3 usable .*vad=silero"):
            await runtime.enrollment.enroll_voice()  # nobody speaks
        runtime.hardware.room.stage_owner(voice_samples=5)
        assert await runtime.enrollment.enroll_voice(progress=seen.append) == 3

    await drive(runtime, body)
    collected = [p.collected for p in seen]
    assert collected == sorted(collected) and collected[-1] == 3  # a short segment may count 0
    assert seen[-1].modality is Biometric.VOICE and seen[-1].frames >= 3
