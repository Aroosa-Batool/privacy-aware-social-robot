"""Enrolment progress, guidance and failure messages, in simulation on the virtual clock."""

import pytest

from pasr.domain.enums import Biometric, Direction, FacePose
from pasr.orchestration.enrollment import (
    FACE_LEARNED,
    POSE_REQUESTS,
    SAMPLE_INTERVAL_S,
    TRY_AGAIN,
    VOICE_FAILED,
    VOICE_LEARNED,
    EnrollmentError,
    EnrollProgress,
)
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from support import room as room_module
from support.clock import VirtualClock
from support.room import OWNER_TAG, POSE_MOVES


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


async def enroll_face(runtime: Runtime, progress=None) -> int:
    runtime.enrollment.register("Owner")
    return await runtime.enrollment.enroll_face(progress=progress)


def events(runtime: Runtime, type: EventType) -> list[dict]:
    return [dict(e.data) for e in runtime.bus.recent if e.type is type]


def spoken(runtime: Runtime) -> list[str]:
    return [line.text for line in runtime.hardware.room.spoken]


async def test_the_robot_asks_for_each_pose_takes_images_of_each_and_says_so(runtime: Runtime):
    seen: list[EnrollProgress] = []
    identity = runtime.settings.identity
    per_pose, poses = identity.enroll_face_samples, identity.enroll_face_poses
    wanted = per_pose * len(poses)
    assert (per_pose, poses) == (4, list(FacePose))

    assert await drive(runtime, lambda: enroll_face(runtime, seen.append)) == wanted
    assert spoken(runtime) == [POSE_REQUESTS[pose] for pose in poses] + [FACE_LEARNED]
    assert [p.collected for p in seen] == list(range(1, wanted + 1))
    assert [p.pose for p in seen] == [pose for pose in poses for _ in range(per_pose)]
    assert all(p.modality is Biometric.FACE and p.wanted == wanted for p in seen)
    last = seen[-1]
    assert (last.frames, last.no_face, last.many_faces, last.unusable) == (wanted, 0, 0, 0)
    gaps = [b.elapsed_s - a.elapsed_s for a, b in zip(seen, seen[1:], strict=False)]
    assert min(gaps) >= SAMPLE_INTERVAL_S  # images of one pose are spread out
    assert runtime.hardware.room.camera_on is False

    logged = events(runtime, EventType.FACE_POSE_CAPTURED)
    assert [e["pose"] for e in logged] == [pose.value for pose in poses]
    assert all(e["samples"] == e["frames"] == 4 and e["reason"] is None for e in logged)
    assert logged[1]["turned"] == pytest.approx(0.3)  # how far the owner turned to the left
    assert logged[3]["tilt"] == pytest.approx(-0.1)  # and raised the chin


async def test_poses_not_taken_are_coached_retried_then_left_out(runtime: Runtime):
    runtime.hardware.room.follows_guidance = False  # the owner keeps looking straight ahead

    assert await drive(runtime, lambda: enroll_face(runtime)) == 4  # the front pose only
    said = spoken(runtime)
    assert "Please turn your head a bit further to your left." in said  # says what is wrong
    assert "Please tilt your chin up a bit more." in said
    assert said.count(TRY_AGAIN) == 4  # every missed pose once more, at the end
    assert said[-1] == (
        "Thank you, I have learned your face. But I could not see you turned to your left or "
        "turned to your right or with your chin up or with your chin down; capture your face "
        "again to add that."
    )
    left = events(runtime, EventType.FACE_POSE_CAPTURED)[1]
    assert (left["pose"], left["samples"], left["reason"]) == ("left", 0, "too little")
    assert left["turned"] == 0 and left["frames"] == left["unusable"] > 0
    assert len(runtime.repos.owner.embeddings(Biometric.FACE)) == 4


async def test_either_side_may_be_the_owners_left_but_not_both(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
):
    mirrored = {pose: (-turn, -chin) for pose, (turn, chin) in POSE_MOVES.items()}
    monkeypatch.setattr(room_module, "POSE_MOVES", mirrored)

    async def body():
        assert await enroll_face(runtime) == 20  # a mirrored camera works
        monkeypatch.setattr(
            room_module, "POSE_MOVES", {**mirrored, FacePose.RIGHT: mirrored[FacePose.LEFT]}
        )
        assert await runtime.enrollment.enroll_face() == 16  # turned the same way twice

    await drive(runtime, body)
    assert "The other way, please: turn your head to your right." in spoken(runtime)
    right = events(runtime, EventType.FACE_POSE_CAPTURED)[-3]
    assert (right["pose"], right["samples"], right["reason"]) == ("right", 0, "wrong way")


async def test_without_the_front_pose_nothing_is_stored_and_the_robot_says_why(
    runtime: Runtime,
):
    room = runtime.hardware.room
    seen: list[EnrollProgress] = []

    async def body():
        runtime.enrollment.register("Owner")
        room.set_faces(Direction.FRONT, [])
        with pytest.raises(EnrollmentError, match="saw no face in .* frames: check"):
            await runtime.enrollment.enroll_face()
        room.set_faces(Direction.FRONT, [OWNER_TAG, "friend"])
        with pytest.raises(EnrollmentError, match="no face in 0, several faces in [1-9]"):
            await runtime.enrollment.enroll_face()
        room.set_faces(Direction.FRONT, [OWNER_TAG])
        room.place(OWNER_TAG, size=0.1)  # too far away: too small to compare well
        with pytest.raises(EnrollmentError, match="mostly 'too small'.*Nothing was stored"):
            await runtime.enrollment.enroll_face(progress=seen.append)

    await drive(runtime, body)
    assert seen[-1].collected == 0 and seen[-1].unusable == seen[-1].frames > 0
    assert {p.pose for p in seen} == {FacePose.FRONT}  # stopped after asking twice for it
    finals = [line for line in spoken(runtime) if line.startswith("Sorry")]
    assert finals == [
        "Sorry, I could not learn your face. I cannot see your face. Please sit in front of "
        "me. Please try once more.",
        "Sorry, I could not learn your face. I can see more than one face. Please make sure "
        "you are alone. Please try once more.",
        "Sorry, I could not learn your face. Please come a little closer to me. Please try "
        "once more.",
    ]
    failed = events(runtime, EventType.OWNER_ENROLMENT_FAILED)
    assert [e["reason"] for e in failed] == ["no_face", "several_faces", "too small"]
    assert runtime.repos.owner.embeddings(Biometric.FACE) == []


async def test_voice_progress_timeout_message_and_spoken_outcome(runtime: Runtime):
    seen: list[EnrollProgress] = []

    async def body():
        runtime.enrollment.register("Owner")
        with pytest.raises(EnrollmentError, match="heard only 0 of 3 usable .*vad=silero"):
            await runtime.enrollment.enroll_voice()  # nobody speaks
        assert spoken(runtime)[-1] == VOICE_FAILED
        runtime.hardware.room.stage_owner(voice_samples=5)
        assert await runtime.enrollment.enroll_voice(progress=seen.append) == 3
        assert spoken(runtime)[-1] == VOICE_LEARNED

    await drive(runtime, body)
    collected = [p.collected for p in seen]
    assert collected == sorted(collected) and collected[-1] == 3  # a short segment may count 0
    assert seen[-1].modality is Biometric.VOICE and seen[-1].frames >= 3
    (failed,) = events(runtime, EventType.OWNER_ENROLMENT_FAILED)
    assert failed == {"modality": "voice", "reason": "too little speech", "samples": 0}
