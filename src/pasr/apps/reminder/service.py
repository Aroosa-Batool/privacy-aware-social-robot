"""Creating and managing reminders. Usable with or without a running robot (CLI, dashboard)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from pasr.domain.enums import ReminderOrigin, ReminderStatus
from pasr.domain.models import Reminder
from pasr.orchestration.clock import Clock
from pasr.orchestration.events import EventBus, EventType
from pasr.perception.bundle import PerceptionBundle
from pasr.perception.protocols import SensitivityResult
from pasr.perception.registry import PluginKind
from pasr.settings.schema import Settings
from pasr.storage.repos import Repositories

PAST_TOLERANCE = timedelta(minutes=1)
DATE_QUESTION = "On what date should I remind you?"


class ReminderError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReminderDraft:
    title: str
    date: date | None
    time: time | None

    @property
    def needs_date(self) -> bool:
        return self.date is None


class ReminderService:
    def __init__(
        self,
        *,
        repos: Repositories,
        perception: PerceptionBundle,
        clock: Clock,
        bus: EventBus,
        settings: Callable[[], Settings],
    ) -> None:
        self.repos = repos
        self.perception = perception
        self.clock = clock
        self.bus = bus
        self._settings = settings

    def draft(self, text: str) -> ReminderDraft:
        if not text.strip():
            raise ReminderError("the reminder is empty")
        parsed = self.perception.datetime_parser.parse(text, self.clock.now())
        return ReminderDraft(parsed.title, parsed.date, parsed.time)

    def answer_date(self, draft: ReminderDraft, answer: str) -> ReminderDraft:
        """Fill in the date from the owner's answer to the counter-question."""
        parsed = self.perception.datetime_parser.parse(answer, self.clock.now())
        if parsed.date is None:
            raise ReminderError(f"could not find a date in {answer!r}")
        return replace(draft, date=parsed.date, time=draft.time or parsed.time)

    def due_at(self, draft: ReminderDraft) -> datetime:
        if draft.date is None:
            raise ReminderError("the reminder has no date")
        at = draft.time or self._settings().reminder.default_time
        return datetime.combine(draft.date, at, tzinfo=self.clock.now().tzinfo)

    def classify(self, title: str) -> SensitivityResult:
        """Blocking (the classifier may be a model): on the robot, run it with
        ``RobotContext.compute``."""
        return self.perception.sensitivity.classify(title)

    def save(
        self,
        draft: ReminderDraft,
        *,
        origin: ReminderOrigin,
        sensitive: bool | SensitivityResult | None = None,
    ) -> Reminder:
        return self.create(draft.title, self.due_at(draft), origin=origin, sensitive=sensitive)

    def create(
        self,
        title: str,
        due_at: datetime,
        *,
        origin: ReminderOrigin,
        sensitive: bool | SensitivityResult | None = None,
    ) -> Reminder:
        """``sensitive``: the owner's choice, the classifier's result, or ``None`` to classify
        the title now."""
        now = self.clock.now()
        if due_at < now - PAST_TOLERANCE:
            raise ReminderError(f"that time ({due_at:%Y-%m-%d %H:%M}) is in the past")
        if sensitive is None:
            sensitive = self.classify(title)
        if isinstance(sensitive, SensitivityResult):
            score: float | None = sensitive.score
            source = self.perception.plugin_name(PluginKind.SENSITIVITY)
            sensitive = sensitive.sensitive
        else:
            score, source = None, "user"
        reminder = self.repos.reminders.add(
            title=title.strip(),
            due_at=due_at,
            sensitive=sensitive,
            sensitivity_score=score,
            sensitivity_source=source,
            origin=origin,
            now=now,
        )
        self.bus.emit(
            EventType.REMINDER_CREATED,
            reminder_id=reminder.id,
            sensitive=sensitive,
            origin=origin.value,
        )
        return reminder

    def cancel(self, reminder_id: int) -> None:
        self.repos.reminders.set_status(reminder_id, ReminderStatus.CANCELLED)

    def delete(self, reminder_id: int) -> bool:
        return self.repos.reminders.delete(reminder_id)

    def upcoming(self) -> list[Reminder]:
        return self.repos.reminders.all([ReminderStatus.SCHEDULED, ReminderStatus.ACTIVE])


def confirmation(reminder: Reminder) -> str:
    """What the robot says after saving. A sensitive title is never repeated out loud."""
    when = f"{reminder.due_at:%A %d %B} at {reminder.due_at:%H:%M}"
    if reminder.sensitive:
        return f"Okay. I saved a private reminder for {when}."
    return f"Okay. I will remind you about {reminder.title} on {when}."
