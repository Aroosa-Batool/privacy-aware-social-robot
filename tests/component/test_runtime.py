import asyncio
from datetime import datetime, timedelta

import pytest

from conftest import stand_ins
from pasr.apps.reminder.capture import VoiceReminderCapture
from pasr.apps.reminder.due_flow import DueState
from pasr.apps.reminder.service import DATE_QUESTION
from pasr.domain.enums import (
    Biometric,
    DeliveryChannel,
    DetectionModality,
    Direction,
    ReminderOrigin,
    ReminderStatus,
    WatchAnswer,
)
from pasr.orchestration.enrollment import VOICE_CHUNK_SECONDS, EnrollmentError
from pasr.orchestration.events import EventType
from pasr.orchestration.handle import RuntimeHandle
from pasr.orchestration.lock import RuntimeBusyError
from pasr.orchestration.runtime import Runtime
from pasr.settings.schema import Settings
from support.clock import VirtualClock
from support.room import OWNER_TAG


async def drive(runtime: Runtime, coro_fn):
    clock = runtime.clock
    assert isinstance(clock, VirtualClock)

    async def main():
        await runtime.start()
        try:
            return await coro_fn()
        finally:
            await runtime.stop()

    return await clock.drive(main())


async def enroll(runtime: Runtime) -> None:
    runtime.enrollment.register("Owner")
    runtime.hardware.room.stage_owner(voice_seconds=runtime.settings.identity.enroll_voice_seconds)
    await runtime.enrollment.enroll_voice()
    await runtime.enrollment.enroll_face()


async def test_enrolment_needs_a_registered_owner(runtime: Runtime):
    async def body():
        with pytest.raises(EnrollmentError, match="register"):
            await runtime.enrollment.enroll_face()

    await drive(runtime, body)


async def test_face_enrolment_refuses_crowded_frames(runtime: Runtime):
    async def body():
        runtime.enrollment.register("Owner")
        runtime.hardware.room.set_faces(Direction.FRONT, [OWNER_TAG, "friend"])
        with pytest.raises(EnrollmentError, match="several faces in [1-9]"):
            await runtime.enrollment.enroll_face()
        assert runtime.repos.owner.embeddings(Biometric.FACE) == []

    await drive(runtime, body)


async def test_enrolment_stores_only_embeddings(runtime: Runtime):
    async def body():
        await enroll(runtime)
        counts = runtime.repos.owner.enrollment()
        identity = runtime.settings.identity
        faces = identity.enroll_face_samples * len(identity.enroll_face_poses)
        assert counts[Biometric.FACE][0] == faces
        # samples of about VOICE_CHUNK_SECONDS of speech each
        assert counts[Biometric.VOICE][0] >= identity.enroll_voice_seconds // VOICE_CHUNK_SECONDS
        assert runtime.hardware.room.camera_on is False  # camera released after enrolment

    await drive(runtime, body)


async def test_voice_capture_asks_for_the_date_and_keeps_sensitive_titles_quiet(runtime: Runtime):
    async def body():
        room, clock = runtime.hardware.room, runtime.clock
        capture = VoiceReminderCapture(runtime.ctx, runtime.service)
        start = clock.now()
        room.speak(
            OWNER_TAG, 2.5, text="doctor appointment at 2pm", start=start + timedelta(seconds=4)
        )
        room.speak(OWNER_TAG, 1.5, text="tomorrow", start=start + timedelta(seconds=12))
        result = await capture.capture()
        assert result.reminder is not None, result.problem
        reminder = result.reminder
        assert reminder.sensitive
        assert reminder.origin is ReminderOrigin.VOICE
        due = reminder.due_at.astimezone(start.tzinfo)  # the database returns local time
        assert (due.date() - start.date()).days == 1
        assert (due.hour, due.minute) == (14, 0)
        said = [line.text for line in room.spoken]
        assert DATE_QUESTION in said
        assert "doctor" not in said[-1].lower()  # the confirmation never repeats it

    await drive(runtime, body)


async def test_voice_capture_with_silence(runtime: Runtime):
    async def body():
        result = await VoiceReminderCapture(runtime.ctx, runtime.service).capture()
        assert result.reminder is None

    await drive(runtime, body)


class ExplodingFace:
    def detect_and_embed(self, frame):
        raise RuntimeError("model crashed")


async def test_perception_errors_fail_closed_to_the_watch(runtime: Runtime):
    async def body():
        await enroll(runtime)
        runtime.perception.__dict__["face"] = ExplodingFace()
        reminder = runtime.service.create(
            "Dentist", runtime.clock.now() + timedelta(minutes=10), origin=ReminderOrigin.CLI
        )
        outcome = await runtime.reminders.wait_for(reminder.id)
        assert outcome.states[-1] is DueState.FAILED
        assert outcome.channel is DeliveryChannel.WATCH
        assert outcome.error == "RuntimeError"
        assert not any(
            line.text.startswith("Here is your") for line in runtime.hardware.room.spoken
        )
        assert runtime.hardware.room.watch_notifications[-1].text == "Reminder: Dentist"
        assert runtime.repos.reminders.get(reminder.id).status is ReminderStatus.SENT_TO_WATCH
        flow = runtime.latest_flow()  # what the dashboard shows
        assert flow is not None and flow.finished
        assert (flow.state, flow.delivered, flow.problem) == ("FAILED", "watch", "model crashed")
        assert not any("model crashed" in str(e.data) for e in runtime.bus.recent)  # memory only

    await drive(runtime, body)


async def test_the_dashboard_sees_what_turned_a_reminder_to_the_watch(runtime: Runtime):
    from pasr.dashboard.components.pipeline import stages

    async def body():
        no_sensors = {"detection_modality": DetectionModality.NONE}
        privacy = runtime.settings.privacy.model_copy(update=no_sensors)
        runtime.ctx.settings = runtime.settings.model_copy(update={"privacy": privacy})
        runtime.hardware.room.script_answer(WatchAnswer.NO)
        due = runtime.clock.now() + timedelta(minutes=10)
        reminder = runtime.service.create("Doctor", due, origin=ReminderOrigin.CLI, sensitive=True)
        await runtime.reminders.wait_for(reminder.id)
        flow = runtime.latest_flow()
        assert flow is not None
        assert (flow.planned, flow.answer, flow.delivered) == ("watch", "no", "watch")
        consent, deliver = stages(flow)[-2:]
        assert (consent.progress, consent.word) == ("done", "said no")  # their decision, followed
        assert (deliver.progress, deliver.word) == ("done", "to watch")

    await drive(runtime, body)


async def test_camera_only_wakes_when_the_listening_would_have_ended(runtime: Runtime):
    async def body():
        due = runtime.clock.now() + timedelta(minutes=10)
        reminder = runtime.service.create("Doctor", due, origin=ReminderOrigin.CLI, sensitive=True)
        timing = runtime.settings.reminder
        lead = timedelta(minutes=timing.wake_lead_minutes)
        assert due - runtime.reminders.start_time(reminder) == lead  # it listens first
        camera_only = {"detection_modality": DetectionModality.CAMERA_ONLY}
        privacy = runtime.settings.privacy.model_copy(update=camera_only)
        runtime.ctx.settings = runtime.settings.model_copy(update={"privacy": privacy})
        window = timedelta(minutes=timing.listen_window_minutes)
        assert due - runtime.reminders.start_time(reminder) == lead - window  # scans as late

    await drive(runtime, body)


def entered(runtime: Runtime) -> dict[DueState, datetime]:
    """When the last flow entered each state."""
    flow = runtime.reminders.last
    assert flow is not None
    return {t.target: t.at for t in flow.fsm.history}


def assert_scanned_in_the_last_30_percent(runtime: Runtime, due: datetime) -> None:
    at = entered(runtime)
    listened = at[DueState.SCANNING] - at[DueState.LISTENING]
    assert abs(listened - 0.7 * (due - at[DueState.LISTENING])) < timedelta(seconds=1)
    assert at[DueState.NO_BYSTANDER] <= due  # scanned until, not past, the due time
    assert at[DueState.DISCLOSE_SPEAK] == due  # so it is not said late


@pytest.mark.parametrize("origin", list(ReminderOrigin))
async def test_due_in_under_7_minutes_it_scans_in_the_last_30_percent_of_the_time_left(
    runtime: Runtime, origin: ReminderOrigin
):
    async def body():
        await enroll(runtime)
        due = runtime.clock.now() + timedelta(seconds=45)
        reminder = runtime.service.create("Doctor", due, origin=origin, sensitive=True)
        await runtime.reminders.wait_for(reminder.id)
        assert_scanned_in_the_last_30_percent(runtime, due)

    await drive(runtime, body)


async def test_a_reminder_typed_for_5_minutes_from_now_scans_before_it_is_due(runtime: Runtime):
    async def body():
        await enroll(runtime)
        draft = runtime.service.draft("Doctor call in 5 minutes")
        reminder = await runtime.reminders.save(
            draft, origin=ReminderOrigin.DASHBOARD, sensitive=True
        )
        in_5_minutes = runtime.clock.now() + timedelta(minutes=5)
        assert abs(reminder.due_at - in_5_minutes) < timedelta(seconds=1)
        await runtime.reminders.wait_for(reminder.id)
        assert_scanned_in_the_last_30_percent(runtime, reminder.due_at)

    await drive(runtime, body)


async def test_on_time_it_listens_for_the_whole_window_then_scans(runtime: Runtime):
    async def body():
        await enroll(runtime)
        due = runtime.clock.now() + timedelta(minutes=10)
        reminder = runtime.service.create("Doctor", due, origin=ReminderOrigin.CLI, sensitive=True)
        await runtime.reminders.wait_for(reminder.id)
        at = entered(runtime)
        window = timedelta(minutes=runtime.settings.reminder.listen_window_minutes)
        listened = at[DueState.SCANNING] - at[DueState.LISTENING]
        assert abs(listened - window) < timedelta(seconds=1)

    await drive(runtime, body)


async def test_what_goes_wrong_while_it_runs_is_kept_for_the_dashboards_toasts(runtime: Runtime):
    loop = asyncio.get_running_loop()

    async def body():
        def broken() -> None:
            raise ValueError("bad frame")

        loop.call_soon(broken)  # an error nothing catches
        await asyncio.sleep(0)
        await enroll(runtime)
        runtime.hardware.room.leave()  # out of Bluetooth range: the watch does not answer
        reminder = runtime.service.create(
            "Dentist", runtime.clock.now() + timedelta(minutes=10), origin=ReminderOrigin.CLI
        )
        await runtime.reminders.wait_for(reminder.id)
        return [notice.message for notice in runtime.notices.since(0)]

    messages = await drive(runtime, body)
    assert messages[0] == "Something in the robot failed: bad frame."
    assert any(message.startswith("The watch did not answer") for message in messages)
    assert not any("Dentist" in message for message in messages)  # no reminder titles
    assert loop.get_exception_handler() is None  # the loop's own again once stopped


async def test_a_watch_without_the_consent_app_means_the_owner_is_away(runtime: Runtime):
    async def body():
        await enroll(runtime)
        room = runtime.hardware.room
        room.clear_logs()
        runtime.hardware.watch.app_missing = True
        reminder = runtime.service.create(
            "Dentist", runtime.clock.now() + timedelta(minutes=10), origin=ReminderOrigin.CLI
        )
        outcome = await runtime.reminders.wait_for(reminder.id)
        assert outcome.states[:5] == (
            DueState.IDLE,
            DueState.WAKING,
            DueState.CHECKING_PRESENCE,
            DueState.OWNER_AWAY,
            DueState.WAIT_FOR_DUE,
        )
        assert room.microphone_opened == room.camera_opened == 0
        assert not room.spoken
        presence = [e for e in runtime.bus.recent if e.type is EventType.OWNER_PRESENCE]
        assert [e.data["present"] for e in presence] == [False]

    await drive(runtime, body)


async def test_missing_enrolment_fails_closed(runtime: Runtime):
    async def body():
        reminder = runtime.service.create(
            "Doctor", runtime.clock.now() + timedelta(minutes=10), origin=ReminderOrigin.CLI
        )
        outcome = await runtime.reminders.wait_for(reminder.id)
        assert outcome.error == "NotEnrolledError"
        assert outcome.channel is DeliveryChannel.WATCH

    await drive(runtime, body)


async def test_reminders_found_too_late_are_missed(runtime: Runtime):
    async def body():
        reminder = runtime.service.create(
            "Groceries", runtime.clock.now() + timedelta(seconds=30), origin=ReminderOrigin.CLI
        )
        await runtime.reminders.stop()  # the robot is "off" while the reminder passes
        await runtime.clock.sleep(3600)
        await runtime.reminders.start()
        outcome = await runtime.reminders.wait_for(reminder.id)
        assert outcome.channel is None
        assert runtime.repos.reminders.get(reminder.id).status is ReminderStatus.MISSED

    await drive(runtime, body)


async def test_the_next_reminder_counts_the_one_running_and_tags_a_test(runtime: Runtime):
    async def body():
        await enroll(runtime)
        now = runtime.clock.now()
        later = runtime.service.create(
            "Groceries", now + timedelta(hours=2), origin=ReminderOrigin.CLI, sensitive=False
        )
        test = runtime.service.create(
            "Doctor", now + timedelta(seconds=45), origin=ReminderOrigin.TEST, sensitive=True
        )
        runtime.reminders.poke()
        await runtime.clock.sleep(1)  # sensitive: the robot is already listening
        up = runtime.snapshot().next_reminder
        assert (up.reminder_id, up.due_at, up.running, up.test) == (
            test.id,
            test.due_at,
            True,
            True,
        )
        await runtime.reminders.wait_for(test.id)
        up = runtime.snapshot().next_reminder
        assert (up.reminder_id, up.running, up.test) == (later.id, False, False)

    await drive(runtime, body)


async def test_settings_apply_live_or_ask_for_restart(runtime: Runtime, settings: Settings):
    changed = settings.model_copy(deep=True)
    changed.privacy.disclosure_policy = changed.privacy.disclosure_policy.ALWAYS_DISCLOSE
    changed.hardware.camera.index = 3
    assert runtime.apply_settings(changed) == ["hardware"]
    assert runtime.settings.privacy.disclosure_policy.value == "always_disclose"
    assert runtime.settings.hardware.camera.index == 0  # structural: kept until restart


async def test_only_one_runtime_per_data_directory(settings: Settings, clock: VirtualClock):
    first = Runtime(settings, clock=clock, hardware=stand_ins(settings, clock), inline_compute=True)
    second = Runtime(
        settings, clock=clock, hardware=stand_ins(settings, clock), inline_compute=True
    )
    await first.start()
    try:
        with pytest.raises(RuntimeBusyError):
            await second.start()
    finally:
        await first.stop()
    await second.start()
    await second.stop()


async def test_start_fails_closed_without_the_ohbot_library(make_settings, monkeypatch):
    """With the real devices, a missing library is reported when the hardware connects."""
    import sys

    from pasr.hardware.protocols import HardwareNotAvailableError

    monkeypatch.setitem(sys.modules, "ohbot", None)
    runtime = Runtime(make_settings())
    with pytest.raises(HardwareNotAvailableError, match="ohbot library is not installed"):
        await runtime.start()
    await runtime.stop()  # not started: a no-op, and the lock is free again
    with pytest.raises(HardwareNotAvailableError):
        await Runtime(make_settings()).start()


def test_perception_runs_in_a_thread_pool_unless_inline(settings: Settings, clock: VirtualClock):
    threaded = Runtime(settings, clock=clock, hardware=stand_ins(settings, clock))
    assert threaded._executor is not None
    threaded._executor.shutdown()
    inline = Runtime(
        settings, clock=clock, hardware=stand_ins(settings, clock), inline_compute=True
    )
    assert inline._executor is None


def test_runtime_handle_runs_in_a_background_thread(settings: Settings, stand_in_robot):
    handle = RuntimeHandle(lambda: settings)
    handle.start()
    try:
        assert handle.running
        snapshot = handle.snapshot()
        assert snapshot is not None
        assert "No owner registered yet" in snapshot.warnings[0]
        assert handle.call_sync(lambda rt: rt.hardware.room.head_direction) is Direction.FRONT
    finally:
        handle.stop()
    assert not handle.running
    assert handle.snapshot() is None
