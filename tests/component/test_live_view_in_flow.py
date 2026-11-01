"""The live view during enrolment, calibration and reminder flows on stand-in devices: what it
is shown, and what it never is."""

from datetime import timedelta

import pytest

from conftest import stand_ins
from pasr.domain.enums import Direction, FacePose, ReminderOrigin
from pasr.live.feed import Tone
from pasr.orchestration.enrollment import POSE_REQUESTS
from pasr.orchestration.runtime import Runtime
from pasr.settings.schema import Settings
from support.clock import VirtualClock
from support.live import RecordingFeed
from support.room import OWNER_TAG


@pytest.fixture
def watched(settings: Settings, clock: VirtualClock) -> tuple[Runtime, RecordingFeed]:
    feed = RecordingFeed()
    runtime = Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        live=feed,
        inline_compute=True,
        session_id="test",
    )
    return runtime, feed


async def drive(runtime: Runtime, body):
    async def main():
        await runtime.start()
        try:
            return await body()
        finally:
            await runtime.stop()

    return await runtime.clock.drive(main())


async def enroll(runtime: Runtime) -> None:
    runtime.enrollment.register("Owner")
    runtime.hardware.room.stage_owner(
        voice_samples=runtime.settings.identity.enroll_voice_samples + 2
    )
    await runtime.enrollment.enroll_voice()
    await runtime.enrollment.enroll_face()


async def test_enrolment_shows_each_sample(watched):
    runtime, feed = watched
    await drive(runtime, lambda: enroll(runtime))

    assert feed.steps == ["Enrolling the owner's voice", "Enrolling the owner's face"]
    identity = runtime.settings.identity
    voices = [voice.label for voice in feed.voices if voice.tone is Tone.SAMPLE]
    assert voices == [f"Sample {n}/{identity.enroll_voice_samples}" for n in range(1, 4)]
    wanted = identity.enroll_face_samples * len(identity.enroll_face_poses)
    assert [face.label for face in feed.faces] == [
        f"Sample {n}/{wanted}" for n in range(1, wanted + 1)
    ]
    assert feed.notes[0] == POSE_REQUESTS[FacePose.FRONT]  # the frame shows what was asked
    assert feed.chunks  # the microphone level while it listened
    assert feed.snapshot().image is None  # the robot stopped: nothing is held any more


async def test_calibration_shows_each_samples_similarity_to_the_owner(watched):
    runtime, feed = watched

    async def body():
        await enroll(runtime)
        await runtime.calibration.score_face(samples=1, timeout_s=10)
        runtime.hardware.room.set_faces(Direction.FRONT, ["friend"])
        await runtime.calibration.score_face(samples=1, timeout_s=10)

    await drive(runtime, body)
    assert feed.steps[-2:] == ["Calibrating the face threshold"] * 2
    assert feed.details[-2:] == ["", ""]  # no plugin or threshold line under the title
    owner, friend = feed.faces[-10:-5], feed.faces[-5:]  # one for each of the 5 poses
    assert all(face.label.startswith("Sample ") and ": 0." in face.label for face in owner)
    assert {face.tone for face in owner} == {Tone.OWNER}
    assert {face.tone for face in friend} == {Tone.OTHER}


async def test_a_reminder_shows_who_was_heard_and_seen_but_never_its_title(watched):
    runtime, feed = watched

    async def body():
        await enroll(runtime)
        room = runtime.hardware.room
        room.clear_upcoming()
        room.set_faces(Direction.LEFT, ["friend"])  # a silent bystander
        due = runtime.clock.now() + timedelta(minutes=10)
        room.speak(OWNER_TAG, 3.0, start=due - timedelta(minutes=6))
        reminder = runtime.service.create("Dentist", due, origin=ReminderOrigin.CLI)
        before = (len(feed.faces), len(feed.voices))
        await runtime.reminders.wait_for(reminder.id)
        return reminder.id, before

    reminder_id, (faces_before, voices_before) = await drive(runtime, body)

    assert feed.steps[-2:] == [
        f"Reminder #{reminder_id}: listening for other voices",
        f"Reminder #{reminder_id}: scanning the room",
    ]
    assert feed.details[-2:] == ["", ""]  # no plugin or threshold line under the title
    voices = feed.voices[voices_before:]
    assert voices and all(voice.label.startswith("Owner ") for voice in voices)
    faces = [face.label for face in feed.faces[faces_before:]]
    assert any(label.startswith("Owner ") for label in faces)
    assert any(label.startswith("Someone else (owner ") for label in faces)
    assert {"looking left", "looking front", "looking right"} <= set(feed.notes)
    shown = [*feed.steps, *faces, *(voice.label for voice in voices), *feed.notes]
    assert not any("Dentist" in text for text in shown)


async def test_nothing_is_shown_while_the_owner_is_away(watched):
    runtime, feed = watched

    async def body():
        runtime.hardware.watch.app_missing = True
        reminder = runtime.service.create(
            "Dentist", runtime.clock.now() + timedelta(minutes=10), origin=ReminderOrigin.CLI
        )
        await runtime.reminders.wait_for(reminder.id)

    await drive(runtime, body)
    assert feed.steps == [] and feed.faces == [] and feed.chunks == 0
