"""Looking closer at a face during the room scan, on stand-in devices: a face that does not
clearly match the owner is studied over several views before the sweep goes on; with following
on, the head also turns and nods towards it. It fails closed when it cannot see it well."""

from datetime import timedelta
from typing import Any

import pytest

from conftest import stand_ins
from pasr.apps.reminder.due_flow import DueState, FlowOutcome
from pasr.domain.enums import DeliveryChannel, Direction, ReminderOrigin
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from support.clock import VirtualClock
from support.live import RecordingFeed
from support.room import OWNER_TAG, Room

SCAN_TO_DELIVERY = [DueState.SCANNING, DueState.VISUAL_BYSTANDER, DueState.CHECK_MEMORY]


def robot(
    make_settings, clock: VirtualClock, scan: dict[str, Any] | None = None, **follow: Any
) -> tuple[Runtime, RecordingFeed]:
    settings = make_settings(scan={"follow": follow, **(scan or {})})
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


async def remind(runtime: Runtime, stage) -> FlowOutcome:
    """Enrol the owner, let ``stage`` arrange the room, then run a silent sensitive reminder."""

    async def body() -> FlowOutcome:
        runtime.enrollment.register("Owner")
        room: Room = runtime.hardware.room
        room.stage_owner(voice_seconds=runtime.settings.identity.enroll_voice_seconds)
        await runtime.enrollment.enroll_voice()
        await runtime.enrollment.enroll_face()
        room.clear_upcoming()  # nobody speaks: the robot scans the room
        stage(room)
        reminder = runtime.service.create(
            "Therapy session",
            runtime.clock.now() + timedelta(minutes=10),
            origin=ReminderOrigin.CLI,
            sensitive=True,
        )
        return await runtime.reminders.wait_for(reminder.id)

    async def main() -> FlowOutcome:
        await runtime.start()
        try:
            return await body()
        finally:
            await runtime.stop()

    return await runtime.clock.drive(main())


def studied(runtime: Runtime) -> list[dict[str, Any]]:
    return [dict(e.data) for e in runtime.bus.recent if e.type is EventType.FACE_STUDIED]


def stranger_cut_off_at_the_top_left(room: Room) -> None:
    room.set_faces(Direction.LEFT, ["stranger"])
    room.place("stranger", x=-1.0, y=-0.9)


def owner_cut_off_at_the_right(room: Room) -> None:
    room.place(OWNER_TAG, x=1.05)


async def test_without_following_the_head_stays_while_it_looks_closer(make_settings, clock):
    runtime, feed = robot(make_settings, clock)
    outcome = await remind(runtime, stranger_cut_off_at_the_top_left)
    assert runtime.hardware.head.nudges == []
    (event,) = studied(runtime)
    assert (event["count"], event["ready"], event["identity"]) == (0, False, "new_bystander")
    assert event["frames"] > 1  # several views, not one frame
    assert DueState.VISUAL_BYSTANDER in outcome.states  # the best view still counts
    assert "Not recognised yet: looking closer" in [face.label for face in feed.faces]


async def test_the_head_follows_a_cut_off_face_until_it_is_in_full_view(make_settings, clock):
    runtime, feed = robot(make_settings, clock, enabled=True)
    outcome = await remind(runtime, stranger_cut_off_at_the_top_left)

    nudges = runtime.hardware.head.nudges
    turn, nod = nudges[0]
    assert turn < 0 and nod > 0  # towards the left, and up
    assert sum(n for _, n in nudges) == pytest.approx(0)  # the nod is undone afterwards
    (event,) = studied(runtime)
    assert event["direction"] == "left" and event["ready"] is True and event["count"] == 1
    assert 0 < event["seconds"] < runtime.settings.scan.study_seconds
    assert outcome.states[4:7] == tuple(SCAN_TO_DELIVERY)
    assert outcome.bystanders == 1 and outcome.channel is DeliveryChannel.WATCH

    labels = [face.label for face in feed.faces]
    assert "Not recognised yet: looking closer" in labels
    views = runtime.settings.scan.study_views
    decided = labels.index(f"Looking closer ({views}/{views})") + 1
    assert labels[decided].startswith("Someone else (owner ")
    assert "looking left: looking closer" in feed.notes
    assert not runtime.hardware.room.camera_on


async def test_without_following_a_cut_off_owner_looks_like_someone_else(make_settings, clock):
    runtime, _ = robot(make_settings, clock)
    outcome = await remind(runtime, owner_cut_off_at_the_right)
    assert outcome.bystanders == 1 and outcome.channel is DeliveryChannel.WATCH


async def test_the_owner_seen_cut_off_is_recognised_once_followed(make_settings, clock):
    runtime, _ = robot(make_settings, clock, enabled=True)
    outcome = await remind(runtime, owner_cut_off_at_the_right)
    assert runtime.hardware.head.nudges[0][0] > 0  # turned towards the right
    first = studied(runtime)[0]
    assert (first["ready"], first["identity"]) == (True, "owner")
    assert DueState.NO_BYSTANDER in outcome.states  # so the sweep went on, and found no one
    assert outcome.bystanders == 0 and outcome.channel is DeliveryChannel.SPOKEN


async def test_a_face_in_full_view_is_looked_at_closer_without_moving(make_settings, clock):
    runtime, _ = robot(make_settings, clock, enabled=True)
    outcome = await remind(runtime, lambda room: room.set_faces(Direction.RIGHT, ["stranger"]))
    assert runtime.hardware.head.nudges == []
    (event,) = studied(runtime)
    views = runtime.settings.scan.study_views
    assert (event["ready"], event["count"], event["frames"]) == (True, 0, views)
    assert outcome.bystanders == 1


async def test_a_low_gain_creeps_up_on_the_face(make_settings, clock):
    runtime, _ = robot(make_settings, clock, enabled=True)

    def stage(room: Room) -> None:
        room.set_faces(Direction.LEFT, ["stranger"])
        room.place("stranger", x=-1.1)
        room.field_of_view = (8.0, 1.5)  # the head turns much less than the image suggests

    await remind(runtime, stage)
    (event,) = studied(runtime)
    assert event["ready"] is True and event["count"] >= 2


async def test_a_face_that_stays_turned_away_is_compared_when_time_runs_out(make_settings, clock):
    runtime, feed = robot(make_settings, clock, scan={"study_seconds": 3.0}, enabled=True)

    def stage(room: Room) -> None:
        room.set_faces(Direction.LEFT, ["stranger"])
        room.place("stranger", turned=0.8)  # centred, so the head has nowhere to go

    outcome = await remind(runtime, stage)
    assert runtime.hardware.head.nudges == []
    (event,) = studied(runtime)
    assert event["ready"] is False and event["count"] == 0
    assert event["seconds"] == pytest.approx(3.0, abs=0.2)  # no hurry, up to study_seconds
    assert "Not in full view (unclear, turned away)" in [face.label for face in feed.faces]
    assert outcome.bystanders == 1  # fails closed: still counts as a bystander


async def test_a_face_lost_by_turning_the_wrong_way_still_counts(make_settings, clock):
    runtime, feed = robot(make_settings, clock, enabled=True, invert_turn=True)
    outcome = await remind(runtime, stranger_cut_off_at_the_top_left)
    assert runtime.hardware.head.nudges[0][0] > 0  # away from the face, which leaves the image
    (event,) = studied(runtime)
    assert event["ready"] is False
    assert "looking left: looking closer: lost it" in feed.notes
    assert outcome.bystanders == 1 and outcome.channel is DeliveryChannel.WATCH
