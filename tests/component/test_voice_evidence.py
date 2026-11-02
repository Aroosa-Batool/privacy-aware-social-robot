"""How much speech the robot needs, on stand-in devices, before it decides that a voice is
someone else's: one short segment is not enough, the same voice heard again is."""

from datetime import timedelta
from typing import Any

from conftest import stand_ins
from pasr.apps.reminder.due_flow import DueState, FlowOutcome
from pasr.domain.enums import DeliveryChannel, ReminderOrigin, WatchAnswer
from pasr.orchestration.events import EventType
from pasr.orchestration.runtime import Runtime
from support.room import OWNER_TAG, Room

S = DueState


async def test_a_voice_counts_once_enough_of_its_speech_is_heard(make_settings, clock):
    settings = make_settings(privacy={"detection_modality": "audio_only"})
    runtime = Runtime(
        settings,
        clock=clock,
        hardware=stand_ins(settings, clock),
        inline_compute=True,
        session_id="test",
    )
    room: Room = runtime.hardware.room
    needed = settings.identity.min_nonowner_seconds

    async def run_reminder(*voices: tuple[str, float, float]) -> tuple[int, FlowOutcome]:
        """A sensitive reminder due in 10 minutes; ``voices`` speak (who, minutes from now,
        seconds)."""
        now = runtime.clock.now()
        for speaker, minutes, seconds in voices:
            room.speak(speaker, seconds, start=now + timedelta(minutes=minutes))
        reminder = runtime.service.create(
            "Therapy session",
            now + timedelta(minutes=10),
            origin=ReminderOrigin.CLI,
            sensitive=True,
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
        room.stage_owner(voice_seconds=settings.identity.enroll_voice_seconds)
        await runtime.enrollment.enroll_voice()
        room.clear_upcoming()

        # one short sentence by someone else, among the owner's: too little to tell who spoke
        brief, outcome = await run_reminder(
            (OWNER_TAG, 3.0, 3.0), ("stranger", 3.5, needed - 1), (OWNER_TAG, 4.0, 3.0)
        )
        heard = of(brief, EventType.VOICE_IDENTIFIED)
        assert [e["identity"] for e in heard] == ["owner", "new_bystander", "owner"]
        assert heard[1]["seconds"] < needed and heard[1]["level"] > -30  # loud enough, short
        assert of(brief, EventType.VOICE_POOLED) == []  # never enough speech to judge
        assert S.NO_BYSTANDER in outcome.states and outcome.bystanders == 0
        assert outcome.channel is DeliveryChannel.SPOKEN

        # the same voice heard again: together its speech is enough, and it is not the owner
        room.script_answer(WatchAnswer.NO)
        again, outcome = await run_reminder(
            ("stranger", 3.5, needed - 1), ("stranger", 4.0, needed - 1)
        )
        heard = of(again, EventType.VOICE_IDENTIFIED)
        assert [e["identity"] for e in heard] == ["new_bystander", "known_bystander"]
        (pooled,) = of(again, EventType.VOICE_POOLED)
        assert pooled["identity"] == "someone_else" and pooled["samples"] == 2
        assert pooled["seconds"] >= needed and pooled["similarity"] < 0.35
        assert outcome.states[3:6] == (S.LISTENING, S.AUDIO_BYSTANDER, S.CHECK_MEMORY)
        assert outcome.bystanders == 1 and outcome.channel is DeliveryChannel.WATCH

    async def main() -> None:
        await runtime.start()
        try:
            await body()
        finally:
            await runtime.stop()

    await runtime.clock.drive(main())
