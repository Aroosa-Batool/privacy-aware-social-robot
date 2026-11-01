"""Setting a reminder by voice, including the counter-question when no date was given."""

from __future__ import annotations

from contextlib import aclosing
from dataclasses import dataclass
from datetime import timedelta

from pasr.apps.reminder.service import (
    DATE_QUESTION,
    ReminderError,
    ReminderService,
    confirmation,
)
from pasr.domain.enums import ReminderOrigin
from pasr.domain.models import Reminder
from pasr.orchestration.context import RobotContext

OPENING = "What should I remind you about?"
LISTEN_TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class CaptureResult:
    reminder: Reminder | None
    problem: str | None = None


class VoiceReminderCapture:
    def __init__(self, ctx: RobotContext, service: ReminderService) -> None:
        self.ctx = ctx
        self.service = service

    async def capture(self) -> CaptureResult:
        say = self.ctx.hardware.speaker.say
        await say(OPENING)
        text = await self._listen()
        if not text:
            await say("Sorry, I didn't hear anything.")
            return CaptureResult(None, "nothing heard")
        try:
            draft = self.service.draft(text)
            if draft.needs_date:
                await say(DATE_QUESTION)
                answer = await self._listen()
                if not answer:
                    await say("Sorry, I didn't hear a date.")
                    return CaptureResult(None, "no date heard")
                draft = self.service.answer_date(draft, answer)
            judged = await self.ctx.compute(self.service.classify, draft.title)
            reminder = self.service.save(draft, origin=ReminderOrigin.VOICE, sensitive=judged)
        except ReminderError as exc:
            await say("Sorry, I couldn't set that reminder.")
            return CaptureResult(None, str(exc))
        await say(confirmation(reminder))
        return CaptureResult(reminder)

    async def _listen(self) -> str:
        """Transcript of the first usable speech segment; the audio itself is discarded."""
        ctx = self.ctx
        until = ctx.clock.now() + timedelta(seconds=LISTEN_TIMEOUT_S)
        min_seconds = ctx.settings.identity.min_voice_segment_seconds / 2
        async with aclosing(ctx.speech_segments(until)) as segments:
            async for segment in segments:
                if segment.duration_s >= min_seconds:
                    text = await ctx.compute(ctx.perception.stt.transcribe, segment)
                    return text.strip()
        return ""
