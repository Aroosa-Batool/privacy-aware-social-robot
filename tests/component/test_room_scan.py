"""The room scan on stand-in devices: row by row, every direction, again and again until the
due time; it stops once it has recognised someone other than the owner."""

import itertools
from datetime import datetime, timedelta
from typing import Any

from conftest import stand_ins
from pasr.apps.reminder.due_flow import DueState, FlowOutcome, scan_path
from pasr.domain.enums import DeliveryChannel, Direction, ReminderOrigin, Tilt, WatchAnswer
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from support.clock import VirtualClock
from support.devices import TILT_NODS
from support.room import Room

LEVEL, UP, DOWN = 0.0, 1.0, -1.0
ROW = [Direction.RIGHT, Direction.FRONT, Direction.LEFT]


def robot(make_settings, clock: VirtualClock) -> Runtime:
    settings = make_settings()
    return Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        inline_compute=True,
        session_id="test",
    )


async def remind(runtime: Runtime, stage, *, due_in: timedelta) -> tuple[FlowOutcome, datetime]:
    """Enrol the owner's face, let ``stage`` arrange the room, then run a silent sensitive
    reminder due in ``due_in``."""

    async def body() -> tuple[FlowOutcome, datetime]:
        runtime.enrollment.register("Owner")
        await runtime.enrollment.enroll_face()
        stage(runtime.hardware.room)
        due = runtime.clock.now() + due_in
        reminder = runtime.service.create(
            "Therapy session", due, origin=ReminderOrigin.CLI, sensitive=True
        )
        return await runtime.reminders.wait_for(reminder.id), due

    async def main() -> tuple[FlowOutcome, datetime]:
        await runtime.start()
        try:
            return await body()
        finally:
            await runtime.stop()

    return await runtime.clock.drive(main())


def entered(runtime: Runtime, state: DueState) -> datetime:
    return next(
        e.ts
        for e in runtime.bus.recent
        if e.type is EventType.FLOW_STATE and e.state_to == state.value
    )


def scanned(runtime: Runtime) -> dict[str, Any]:
    (event,) = [e for e in runtime.bus.recent if e.type is EventType.ROOM_SCANNED]
    return dict(event.data)


def scan_views(runtime: Runtime) -> list[tuple[float, Direction]]:
    """The head's views from the scan's start (and its looks to the front after it)."""
    views = runtime.hardware.head.views
    start = next(i for i, view in enumerate(views) if view == (LEVEL, Direction.RIGHT))
    return views[start:]


def walk(path, steps: int, head: list[Direction | None]) -> list[tuple[Tilt, Direction]]:
    """The first ``steps`` views of ``path``, the head pointing at each in turn."""
    views = []
    for view in itertools.islice(path, steps):
        views.append(view)
        head[0] = view[1]
    return views


def test_each_row_starts_where_the_head_is_so_it_never_swings_back_across_the_room():
    head: list[Direction | None] = [None]
    views = walk(scan_path([Tilt.LEVEL, Tilt.UP], ROW, lambda: head[0]), 9, head)
    assert [d for _, d in views] == ROW + ROW[::-1] + ROW  # it goes on the same way each sweep
    assert [t for t, _ in views] == [Tilt.LEVEL] * 3 + [Tilt.UP] * 3 + [Tilt.LEVEL] * 3
    assert all(a[1] == b[1] for a, b in itertools.pairwise(views) if a[0] != b[0])  # only nods


def test_where_the_head_ends_up_decides_not_a_fixed_pattern():
    head: list[Direction | None] = [None]
    path = scan_path([Tilt.LEVEL, Tilt.UP, Tilt.DOWN], ROW, lambda: head[0])
    assert [d for _, d in walk(path, 3, head)] == ROW  # from the front: in the given order
    head[0] = Direction.RIGHT  # say, a closer look at a face left the head on the right
    assert [d for _, d in walk(path, 3, head)] == ROW  # so the next row starts on the right
    head[0] = Direction.FRONT  # both ends as near: the given order
    assert [d for _, d in walk(path, 3, head)] == ROW


async def test_the_scan_sweeps_each_row_until_the_due_time(make_settings, clock):
    runtime = robot(make_settings, clock)
    outcome, due = await remind(runtime, lambda room: None, due_in=timedelta(minutes=10))

    views = scan_views(runtime)
    back = ROW[::-1]
    # level, then up, then down; each row the other way, so the head only nods between rows
    assert views[:9] == [(LEVEL, d) for d in ROW] + [(UP, d) for d in back] + [
        (DOWN, d) for d in ROW
    ]
    assert views[9:18] == [(LEVEL, d) for d in back] + [(UP, d) for d in ROW] + [
        (DOWN, d) for d in back
    ]  # and again, starting where the last sweep ended
    scan = scanned(runtime)
    assert scan["reason"] == "found no one" and scan["count"] >= 5
    started = entered(runtime, DueState.SCANNING)
    assert due - started >= timedelta(minutes=2) - timedelta(seconds=1)  # the last 2 minutes
    stopped = entered(runtime, DueState.NO_BYSTANDER)
    assert due - timedelta(seconds=3) <= stopped <= due  # looked until, not past, the due time
    path = [e for e in runtime.bus.recent if e.type is EventType.FLOW_STATE]
    reason = next(e.data["reason"] for e in path if e.state_to == "NO_BYSTANDER")
    assert reason == f"found no one: {scan['count']} full sweep(s) until the due time"
    assert outcome.channel is DeliveryChannel.SPOKEN
    assert not runtime.hardware.room.camera_on
    assert runtime.hardware.room.head_offset == (0.0, TILT_NODS["level"])  # level again


async def test_someone_seen_only_with_the_head_up_is_found_and_the_scan_stops(make_settings, clock):
    runtime = robot(make_settings, clock)

    def standing_on_the_right(room: Room) -> None:
        room.set_faces(Direction.RIGHT, ["stranger"])
        room.place("stranger", y=-1.3)  # above the image while the head is level

    outcome, due = await remind(runtime, standing_on_the_right, due_in=timedelta(minutes=10))
    views = scan_views(runtime)
    assert views[:6] == [(LEVEL, d) for d in ROW] + [(UP, d) for d in ROW[::-1]]
    assert set(views[6:]) == {(LEVEL, Direction.FRONT)}  # then only back to the front: done
    assert scanned(runtime)["reason"] == "found someone"
    assert entered(runtime, DueState.VISUAL_BYSTANDER) < due - timedelta(seconds=90)
    assert outcome.bystanders == 1 and outcome.channel is DeliveryChannel.WATCH
    assert not runtime.hardware.room.camera_on


async def test_a_late_flow_still_sweeps_the_first_row(make_settings, clock):
    runtime = robot(make_settings, clock)
    outcome, _ = await remind(runtime, lambda room: None, due_in=timedelta(seconds=5))
    assert scan_views(runtime)[:3] == [(LEVEL, d) for d in ROW]
    assert scanned(runtime)["count"] == 0
    reason = next(
        e.data["reason"]
        for e in runtime.bus.recent
        if e.type is EventType.FLOW_STATE and e.state_to == "NO_BYSTANDER"
    )
    assert reason == "found no one: part of a sweep until the due time"
    assert outcome.channel is DeliveryChannel.SPOKEN


async def test_people_allowed_before_do_not_stop_the_scan_but_anyone_else_does(
    make_settings, clock
):
    settings = make_settings(privacy={"disclosure_policy": "ask_once_per_bystander"})
    runtime = Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        inline_compute=True,
        session_id="test",
    )
    room: Room = runtime.hardware.room

    async def run_reminder() -> tuple[int, FlowOutcome]:
        due = runtime.clock.now() + timedelta(minutes=10)
        reminder = runtime.service.create(
            "Therapy session", due, origin=ReminderOrigin.CLI, sensitive=True
        )
        return reminder.id, await runtime.reminders.wait_for(reminder.id)

    def of(reminder_id: int, kind: EventType) -> list[dict[str, Any]]:
        return [
            dict(e.data)
            for e in runtime.bus.recent
            if e.type is kind and e.reminder_id == reminder_id
        ]

    async def body() -> None:
        runtime.enrollment.register("Owner")
        await runtime.enrollment.enroll_face()
        room.set_faces(Direction.RIGHT, ["friend"])

        room.script_answer(WatchAnswer.YES)  # first time: asked, and the owner says yes
        first, outcome = await run_reminder()
        assert of(first, EventType.CONSENT_REQUESTED) and outcome.channel is DeliveryChannel.SPOKEN

        second, outcome = await run_reminder()  # the friend again, nobody else
        assert of(second, EventType.CONSENT_REQUESTED) == []  # not asked again
        (look,) = of(second, EventType.FACE_STUDIED)  # recognised once, then only noted
        assert look["identity"] == "known_bystander"
        (scan,) = of(second, EventType.ROOM_SCANNED)
        assert scan["reason"] == "found only people allowed before" and scan["count"] >= 3
        assert DueState.CHECK_MEMORY in outcome.states
        assert outcome.channel is DeliveryChannel.SPOKEN

        room.set_faces(Direction.LEFT, ["stranger"])
        room.place("stranger", y=-1.3)  # standing: seen only with the head up
        room.script_answer(WatchAnswer.NO)
        third, outcome = await run_reminder()  # the friend, and someone new
        (scan,) = of(third, EventType.ROOM_SCANNED)
        assert scan["reason"] == "found someone"  # it looked past the friend and found them
        identities = [e["identity"] for e in of(third, EventType.FACE_STUDIED)]
        assert identities == ["known_bystander", "new_bystander"]
        assert of(third, EventType.CONSENT_REQUESTED)
        assert outcome.bystanders == 2 and outcome.channel is DeliveryChannel.WATCH

    async def main() -> None:
        await runtime.start()
        try:
            await body()
        finally:
            await runtime.stop()

    await runtime.clock.drive(main())
