"""Listening under the ask-once policy, on stand-in devices: the voice of someone the owner
allowed before does not end the listening or skip the room scan; anyone else does."""

from datetime import timedelta
from typing import Any

from conftest import stand_ins
from pasr.apps.reminder.due_flow import DueState, FlowOutcome
from pasr.domain.enums import DeliveryChannel, ReminderOrigin, WatchAnswer
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from support.room import Room

S = DueState


async def test_allowed_voices_are_noted_and_the_robot_listens_and_looks_on(make_settings, clock):
    settings = make_settings(privacy={"disclosure_policy": "ask_once_per_bystander"})
    runtime = Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        inline_compute=True,
        session_id="test",
    )
    room: Room = runtime.hardware.room

    async def run_reminder(*voices: tuple[str, float]) -> tuple[int, FlowOutcome]:
        """A sensitive reminder due in 10 minutes; ``voices`` speak (who, minutes from now)."""
        now = runtime.clock.now()
        for speaker, minutes in voices:
            room.speak(speaker, 3.0, start=now + timedelta(minutes=minutes))
        reminder = runtime.service.create(
            "Therapy session",
            now + timedelta(minutes=10),
            origin=ReminderOrigin.CLI,
            sensitive=True,
        )
        return reminder.id, await runtime.reminders.wait_for(reminder.id)

    def of(reminder_id: int, kind: EventType) -> list[Any]:
        return [e for e in runtime.bus.recent if e.type is kind and e.reminder_id == reminder_id]

    async def body() -> None:
        runtime.enrollment.register("Owner")
        room.stage_owner(voice_samples=runtime.settings.identity.enroll_voice_samples + 2)
        await runtime.enrollment.enroll_voice()
        await runtime.enrollment.enroll_face()
        room.clear_upcoming()

        room.script_answer(WatchAnswer.YES)  # first time: asked, and the owner says yes
        first, outcome = await run_reminder(("friend", 3.5))
        assert of(first, EventType.CONSENT_REQUESTED)
        assert outcome.channel is DeliveryChannel.SPOKEN

        second, outcome = await run_reminder(("friend", 3.5), ("friend", 5.0))
        assert of(second, EventType.CONSENT_REQUESTED) == []  # not asked again
        heard = [e.data["identity"] for e in of(second, EventType.VOICE_IDENTIFIED)]
        assert heard == ["known_bystander", "known_bystander"]  # listened on after the first
        assert outcome.states[3:9] == (
            S.LISTENING,
            S.AUDIO_BYSTANDER,  # heard only the friend...
            S.SCANNING,  # ...so it still looked for silent people
            S.CHECK_MEMORY,  # saw no one else: the friend is allowed
            S.WAIT_FOR_DUE,
            S.DISCLOSE_SPEAK,
        )
        flow = {e.state_to: e.ts for e in of(second, EventType.FLOW_STATE)}
        listened = flow[S.SCANNING] - flow[S.LISTENING]
        assert abs(listened - timedelta(minutes=5)) < timedelta(seconds=1)  # the whole window

        room.script_answer(WatchAnswer.NO)
        third, outcome = await run_reminder(("friend", 3.5), ("stranger", 4.5))
        assert of(third, EventType.CONSENT_REQUESTED)  # someone new: it asks
        assert S.SCANNING not in outcome.states  # and needs no scan to know
        assert outcome.bystanders == 2 and outcome.channel is DeliveryChannel.WATCH

    async def main() -> None:
        await runtime.start()
        try:
            await body()
        finally:
            await runtime.stop()

    await runtime.clock.drive(main())
