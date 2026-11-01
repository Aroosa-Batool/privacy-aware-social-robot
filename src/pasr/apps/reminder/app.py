from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta

from pasr.apps.reminder.capture import CaptureResult, VoiceReminderCapture
from pasr.apps.reminder.due_flow import DueFlow, DueState, FlowOutcome
from pasr.apps.reminder.service import ReminderDraft, ReminderService
from pasr.domain.enums import ReminderOrigin, ReminderStatus
from pasr.domain.models import Reminder
from pasr.domain.policy import requires_detection
from pasr.domain.timing import flow_start, is_missed
from pasr.orchestration.context import RobotContext
from pasr.orchestration.events import EventType
from pasr.orchestration.scheduler import PollingScheduler
from pasr.perception.protocols import SensitivityResult

logger = logging.getLogger(__name__)


class ReminderApp:
    """Runs due flows from the database, one at a time, in order of start time."""

    name = "reminders"

    def __init__(self, ctx: RobotContext, service: ReminderService) -> None:
        self.ctx = ctx
        self.service = service
        self.capture = VoiceReminderCapture(ctx, service)
        self.scheduler = PollingScheduler(
            ctx.clock, self._tick, lambda: ctx.settings.reminder.poll_interval_seconds
        )
        self.current: DueFlow | None = None
        self.last: DueFlow | None = None
        self.last_outcome: FlowOutcome | None = None
        self._waiters: dict[int, list[asyncio.Future[FlowOutcome]]] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        recovered = self.ctx.repos.reminders.recover_interrupted()
        if recovered:
            logger.info("re-scheduled %d interrupted reminder(s)", recovered)
        self._task = asyncio.create_task(self.scheduler.run(), name="pasr-reminder-scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def poke(self) -> None:
        """Re-read reminders now (after one was added or the clock was moved)."""
        self.scheduler.poke()

    async def save(
        self, draft: ReminderDraft, *, origin: ReminderOrigin, sensitive: bool | None = None
    ) -> Reminder:
        """Save from the robot's loop; a sensitivity model runs on the compute pool."""
        judged: bool | SensitivityResult = (
            sensitive
            if sensitive is not None
            else await self.ctx.compute(self.service.classify, draft.title)
        )
        reminder = self.service.save(draft, origin=origin, sensitive=judged)
        self.poke()
        return reminder

    async def capture_by_voice(self) -> CaptureResult:
        result = await self.capture.capture()
        self.poke()
        return result

    def start_time(self, reminder: Reminder) -> datetime:
        settings = self.ctx.settings
        lead = timedelta(minutes=settings.reminder.wake_lead_minutes)
        if not settings.privacy.detection_modality.listens:  # nothing to listen to: wake when
            # the listening would have ended, so the room is scanned as late as with the mic
            window = timedelta(minutes=settings.reminder.listen_window_minutes)
            lead = max(lead - window, timedelta(0))
        return flow_start(
            reminder.due_at,
            wake_lead=lead,
            needs_detection=requires_detection(
                policy=settings.privacy.disclosure_policy,
                modality=settings.privacy.detection_modality,
                sensitive=reminder.sensitive,
            ),
        )

    def next_up(self) -> Reminder | None:
        """The reminder due soonest, counting the one running now: a quick test or a sensitive
        reminder starts before it is due, and is still the next one until it is delivered."""
        pending = self.ctx.repos.reminders.all([ReminderStatus.SCHEDULED])
        if self.current is not None:
            pending.append(self.current.reminder)
        return min(pending, key=lambda reminder: reminder.due_at, default=None)

    async def wait_for(self, reminder_id: int) -> FlowOutcome:
        future: asyncio.Future[FlowOutcome] = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(reminder_id, []).append(future)
        self.poke()
        return await future

    async def _tick(self) -> datetime | None:
        ctx = self.ctx
        grace = timedelta(minutes=ctx.settings.reminder.missed_grace_minutes)
        next_at: datetime | None = None
        for reminder in ctx.repos.reminders.all([ReminderStatus.SCHEDULED]):
            now = ctx.clock.now()
            if is_missed(reminder.due_at, now, grace=grace):
                ctx.repos.reminders.set_status(reminder.id, ReminderStatus.MISSED)
                ctx.bus.emit(
                    EventType.REMINDER_MISSED,
                    reminder_id=reminder.id,
                    reason="robot was not running",
                )
                self._resolve(FlowOutcome(reminder.id, (DueState.IDLE,), None, 0, "missed"))
                continue
            start = self.start_time(reminder)
            if start <= now:
                await self._run(reminder)
                return ctx.clock.now()  # look again straight away
            next_at = start if next_at is None else min(next_at, start)
        return next_at

    async def _run(self, reminder: Reminder) -> None:
        self.ctx.repos.reminders.set_status(reminder.id, ReminderStatus.ACTIVE)
        flow = DueFlow(self.ctx, reminder)
        self.current = flow
        try:
            outcome = await flow.run()
        finally:
            self.current = None
        self.last, self.last_outcome = flow, outcome
        self._resolve(outcome)

    def _resolve(self, outcome: FlowOutcome) -> None:
        for future in self._waiters.pop(outcome.reminder_id, []):
            if not future.done():
                future.set_result(outcome)
