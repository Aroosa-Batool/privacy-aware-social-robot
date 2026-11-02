"""Calibration on the fakes: owner scores beat strangers, and applying stores only a number."""

import pytest

from pasr.domain.enums import Biometric, Direction
from pasr.orchestration.enrollment import EnrollmentError
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from pasr.settings.loader import read_overrides
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


async def test_scores_separate_owner_from_strangers_and_apply_stores_a_threshold(runtime):
    events = []
    runtime.bus.subscribe(events.append)

    async def body():
        with pytest.raises(EnrollmentError, match="enrol the owner's face first"):
            await runtime.calibration.score_face(samples=3, timeout_s=10)
        runtime.enrollment.register("Owner")
        runtime.hardware.room.stage_owner(
            voice_seconds=runtime.settings.identity.enroll_voice_seconds
        )
        await runtime.enrollment.enroll_voice()
        await runtime.enrollment.enroll_face()

        owner_faces = await runtime.calibration.score_face(samples=2, timeout_s=10)
        runtime.hardware.room.set_faces(Direction.FRONT, ["stranger"])
        other_faces = await runtime.calibration.score_face(samples=2, timeout_s=10)
        runtime.hardware.room.set_faces(Direction.FRONT, [OWNER_TAG])
        assert len(owner_faces) == len(other_faces) == 10  # 2 for each of the 5 poses
        assert min(owner_faces) > max(other_faces)

        runtime.hardware.room.clear_upcoming()
        runtime.hardware.room.stage_speaker("stranger", samples=3)
        other_voices = await runtime.calibration.score_voice(samples=3, timeout_s=20)
        runtime.hardware.room.clear_upcoming()  # the stranger's spare utterance must not leak in
        runtime.hardware.room.stage_speaker(OWNER_TAG, samples=3)
        owner_voices = await runtime.calibration.score_voice(samples=3, timeout_s=20)
        assert min(owner_voices) > max(other_voices)

        before = runtime.repos.owner.enrollment()
        runtime.calibration.apply(Biometric.FACE, 0.4321)
        assert runtime.repos.owner.enrollment() == before  # nothing else stored

    await drive(runtime, body)
    assert read_overrides(runtime.settings.storage.data_dir) == {
        "identity": {"face_threshold": 0.432}
    }
    calibrated = [e for e in events if e.type is EventType.THRESHOLD_CALIBRATED]
    assert len(calibrated) == 1
    assert calibrated[0].data["modality"] == "face" and calibrated[0].data["threshold"] == 0.432
    assert calibrated[0].data["plugin"] == "stand_in"
