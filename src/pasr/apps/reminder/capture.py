"""Setting a reminder by voice: what to remind about, then when, if that was not said (ADR 0015).

A time without a date is today, or tomorrow once it has passed (``ReminderService``). With
neither, the robot asks "When should I remind you?"; with a date only, "At what time should I
remind you?". Each question is asked at most three times: after a miss, with a short apology
and the question again, then also with an example of what to say; after the third miss the
robot says the reminder is not saved.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import timedelta
from functools import partial

from pasr.apps.reminder.service import (
    TIME_QUESTION,
    WHEN_QUESTION,
    ReminderDraft,
    ReminderError,
    ReminderService,
    confirmation,
)
from pasr.domain.enums import ReminderOrigin
from pasr.domain.models import Reminder
from pasr.orchestration.context import RobotContext

OPENING = "What should I remind you about?"
ATTEMPTS = 3
"""Times each question is asked before the robot gives up."""
LISTEN_TIMEOUT_S = 15.0
"""How long the robot waits for an answer to each question."""
END_OF_TURN_MS = 1000
"""The pause that ends an answer. The listening flow's 300 ms cut people off mid-sentence:
"remind me to … call the dentist … on Friday" (ADR 0015)."""
LONGEST_S = 3 * ATTEMPTS * (LISTEN_TIMEOUT_S + 10)
"""The longest a capture can take: three questions, each asked at most ``ATTEMPTS`` times
(saying it, listening, transcribing)."""
NOT_SAVED = "Sorry, the reminder is not saved. Please try again, or type it on the dashboard."
PASSED = "Sorry, that time has already passed, so the reminder is not saved. Please try again."


@dataclass(frozen=True, slots=True)
class Question:
    ask: str
    example: str
    """What the owner could answer, said with the last try."""

    def prompt(self, attempt: int) -> str:
        """The question as asked the first time, then after one and two misses."""
        if attempt == 0:
            return self.ask
        if attempt == 1:
            return f"Sorry, I didn't catch that. {self.ask}"
        example = f"You can say, for example, {self.example}."
        return f"Sorry, I still didn't catch that. {self.ask} {example}"


WHAT = Question(OPENING, "remind me to buy milk tomorrow at 10 AM")
WHEN = Question(WHEN_QUESTION, "tomorrow at 3 PM")
AT_WHAT_TIME = Question(TIME_QUESTION, "at 3 PM")


@dataclass(frozen=True, slots=True)
class CaptureResult:
    reminder: Reminder | None
    problem: str | None = None


class VoiceReminderCapture:
    def __init__(self, ctx: RobotContext, service: ReminderService) -> None:
        self.ctx = ctx
        self.service = service

    async def capture(self) -> CaptureResult:
        draft: ReminderDraft | None = await self._ask(WHAT, self.service.draft)
        if draft is not None and draft.needs_date:  # neither a date nor a time
            draft = await self._ask(WHEN, partial(self.service.answer_when, draft))
        if draft is not None and draft.needs_time:  # a date only
            draft = await self._ask(AT_WHAT_TIME, partial(self._timed, draft))
        if draft is None:
            await self.ctx.hardware.speaker.say(NOT_SAVED)
            return CaptureResult(None, f"not understood after {ATTEMPTS} tries")
        try:
            judged = await self.ctx.compute(self.service.classify, draft.title)
            reminder = self.service.save(draft, origin=ReminderOrigin.VOICE, sensitive=judged)
        except ReminderError as exc:  # a date and time named outright, already gone
            await self.ctx.hardware.speaker.say(PASSED)
            return CaptureResult(None, str(exc))
        await self.ctx.hardware.speaker.say(confirmation(reminder))
        return CaptureResult(reminder)

    def _timed(self, draft: ReminderDraft, answer: str) -> ReminderDraft:
        """The answer to "at what time?" must name a time."""
        answered = self.service.answer_when(draft, answer)
        if answered.needs_time:
            raise ReminderError(f"could not find a time in {answer!r}")
        return answered

    async def _ask(
        self, question: Question, understand: Callable[[str], ReminderDraft]
    ) -> ReminderDraft | None:
        """Ask until an answer is understood, at most ``ATTEMPTS`` times; None if none was.
        Nothing heard and something not understood are both a miss."""
        for attempt in range(ATTEMPTS):
            await self.ctx.hardware.speaker.say(question.prompt(attempt))
            text = await self._listen()
            if not text:
                continue
            try:
                return understand(text)
            except ReminderError:
                continue
        return None

    async def _listen(self) -> str:
        """Transcript of the first usable answer; the audio itself is discarded."""
        ctx = self.ctx
        until = ctx.clock.now() + timedelta(seconds=LISTEN_TIMEOUT_S)
        min_seconds = ctx.settings.identity.min_voice_segment_seconds / 2
        segments = ctx.speech_segments(until, min_silence_ms=END_OF_TURN_MS)
        async with aclosing(segments) as answers:
            async for segment in answers:
                if segment.duration_s >= min_seconds:
                    text = await ctx.compute(ctx.perception.stt.transcribe, segment)
                    return text.strip()
        return ""
