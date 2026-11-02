"""Composition root: builds every part of the robot from settings and runs the apps."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pasr.apps.reminder.app import ReminderApp
from pasr.apps.reminder.due_flow import DueFlow
from pasr.apps.reminder.service import ReminderService
from pasr.domain.enums import Biometric, ReminderOrigin
from pasr.hardware.factory import HardwareBundle, build_hardware
from pasr.live.desktop import DesktopWindow
from pasr.live.feed import LiveFeed
from pasr.orchestration.calibration import CalibrationService
from pasr.orchestration.clock import Clock, SystemClock
from pasr.orchestration.context import RobotContext
from pasr.orchestration.enrollment import EnrollmentService
from pasr.orchestration.events import Event, EventBus, EventType
from pasr.orchestration.lock import RuntimeLock
from pasr.orchestration.notices import Notices, on_loop_error
from pasr.paths import resolve
from pasr.perception.bundle import PerceptionBundle
from pasr.perception.registry import PluginKind
from pasr.settings.loader import as_dict, diff, update_overrides
from pasr.settings.schema import STRUCTURAL_GROUPS, Settings
from pasr.storage.db import Database
from pasr.storage.repos import Repositories

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FlowView:
    reminder_id: int
    state: str
    steps: tuple[tuple[str, datetime, str], ...]
    """(state entered, when, why)"""
    finished: bool
    delivered: str | None = None
    """The channel the reminder reached, once it reached one."""
    problem: str | None = None
    """What went wrong, in words, when the flow failed."""
    planned: str | None = None
    """The channel chosen before the due time (the watch takes over if the owner left)."""
    answer: str | None = None
    """The owner's answer on the watch, once asked for consent."""


@dataclass(frozen=True, slots=True)
class NextReminder:
    reminder_id: int
    due_at: datetime
    starts_at: datetime
    """When the robot starts on it (earlier for a sensitive one: it listens first)."""
    running: bool
    """The robot is on it now."""
    test: bool
    """Added with the dashboard's Quick test."""


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    now: datetime
    session_id: str
    plugins: dict[str, str]
    modality: str
    policy: str
    enrolled: dict[str, int]
    warnings: tuple[str, ...]
    active_flow: FlowView | None
    last_flow: FlowView | None
    next_reminder: NextReminder | None
    events: tuple[Event, ...]


def setup_warnings(settings: Settings, owner: str | None, enrolled: dict[str, int]) -> list[str]:
    warnings = []
    if owner is None:
        warnings.append("No owner registered yet , open Profile.")
    modality = settings.privacy.detection_modality
    if modality.listens and not enrolled.get(Biometric.VOICE.value):
        warnings.append("Owner voice not enrolled: sensitive information will go to the watch.")
    if modality.looks and not enrolled.get(Biometric.FACE.value):
        warnings.append("Owner face not enrolled: sensitive information will go to the watch.")
    return warnings


class Runtime:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Clock | None = None,
        hardware: HardwareBundle | None = None,
        live: LiveFeed | None = None,
        live_window: bool = False,
        inline_compute: bool = False,
        session_id: str | None = None,
    ) -> None:
        """``hardware`` replaces the devices built from ``settings.hardware`` (tests pass
        stand-ins), ``live`` the live view's feed (tests pass one that records).
        ``live_window`` shows the live view in a window on the laptop while
        ``live_view.enabled`` is on (the dashboard and the terminal commands ask for it).
        ``inline_compute`` runs perception on the event loop instead of a thread pool, which a
        virtual clock needs to stay deterministic."""
        self.clock: Clock = clock or SystemClock()
        self.data_dir = resolve(settings.storage.data_dir)
        self.db = Database.in_dir(self.data_dir)
        self.repos = Repositories(self.db)
        self.session_id = session_id or f"run-{self.clock.now():%Y%m%d-%H%M%S}"
        self.bus = EventBus(self.clock, self.session_id, sinks=[self.repos.events.append])
        self.hardware = hardware or build_hardware(
            settings.hardware, clock=self.clock, on_watch_address=self._remember_watch_address
        )
        self.perception = PerceptionBundle(
            settings.perception, models_dir=resolve(settings.storage.models_dir)
        )
        self._executor = (
            None
            if inline_compute
            else ThreadPoolExecutor(settings.hardware.executor_workers, thread_name_prefix="pasr")
        )
        self.live = live or LiveFeed(lambda: self.ctx.settings.live_view.enabled)
        self._live_window = live_window
        self._window_task: asyncio.Task[None] | None = None
        self.ctx = RobotContext(
            settings=settings,
            clock=self.clock,
            hardware=self.hardware,
            perception=self.perception,
            repos=self.repos,
            bus=self.bus,
            live=self.live,
            executor=self._executor,
        )
        self.service = ReminderService(
            repos=self.repos,
            perception=self.perception,
            clock=self.clock,
            bus=self.bus,
            settings=lambda: self.ctx.settings,
        )
        self.reminders = ReminderApp(self.ctx, self.service)
        self.enrollment = EnrollmentService(self.ctx)
        self.calibration = CalibrationService(self.ctx)
        self._lock = RuntimeLock(self.data_dir)
        self.notices = Notices()
        """What went wrong while it ran, for the dashboard's toasts."""
        self._loop_errors: Any = None
        self.started = False

    @property
    def settings(self) -> Settings:
        return self.ctx.settings

    def _remember_watch_address(self, address: str) -> None:
        logger.info("watch found at %s; caching the address", address)
        update_overrides(self.data_dir, {"hardware": {"watch": {"address": address}}})

    async def start(self, *, run_apps: bool = True) -> None:
        """Own the hardware and start the apps (``run_apps=False``: hardware only, e.g. for
        enrolment from the command line)."""
        self._lock.acquire()
        self.notices.attach()  # also what goes wrong while the devices connect
        try:
            self.db.migrate()
            retention = self.settings.storage.event_log_retention_days
            if retention:
                self.repos.events.purge_older_than(self.clock.now() - timedelta(days=retention))
            await self.hardware.connect(watch=run_apps)
            if run_apps:
                await self.reminders.start()
        except BaseException:
            self.notices.detach()
            self._lock.release()
            raise
        loop = asyncio.get_running_loop()
        self._loop_errors = loop.get_exception_handler()
        loop.set_exception_handler(on_loop_error)
        self.started = True
        if self._live_window:
            window = DesktopWindow(self.live).run()
            self._window_task = asyncio.create_task(window, name="pasr-live-window")
        self.bus.emit(EventType.RUNTIME_STARTED)

    async def stop(self) -> None:
        if not self.started:
            return
        self.started = False
        try:
            if self._window_task is not None:
                self._window_task.cancel()  # closes the window
                with contextlib.suppress(asyncio.CancelledError):
                    await self._window_task
                self._window_task = None
            await self.reminders.stop()
            await self.hardware.close()
            self.bus.emit(EventType.RUNTIME_STOPPED)
        finally:
            self.live.clear()
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
            asyncio.get_running_loop().set_exception_handler(self._loop_errors)
            self.notices.detach()
            self._lock.release()

    def apply_settings(self, new: Settings) -> list[str]:
        """Apply changed settings live where possible. Returns groups that need a restart."""
        changed = diff(as_dict(new), as_dict(self.settings))
        restart = sorted(group for group in changed if group in STRUCTURAL_GROUPS)
        keep = {group: getattr(self.settings, group) for group in STRUCTURAL_GROUPS}
        self.ctx.settings = new.model_copy(update=keep)
        if changed:
            self.bus.emit(EventType.SETTINGS_CHANGED, count=len(changed))
            self.reminders.poke()
        return restart

    def snapshot(self) -> RuntimeSnapshot:
        settings = self.settings
        owner = self.repos.owner.get()
        enrolled = {m.value: n for m, (n, _) in self.repos.owner.enrollment().items()}
        next_up, current = self.reminders.next_up(), self.reminders.current
        return RuntimeSnapshot(
            now=self.clock.now(),
            session_id=self.session_id,
            plugins={k.value: self.perception.plugin_name(k) for k in PluginKind},
            modality=settings.privacy.detection_modality.value,
            policy=settings.privacy.disclosure_policy.value,
            enrolled=enrolled,
            warnings=tuple(
                setup_warnings(settings, owner.display_name if owner else None, enrolled)
            ),
            active_flow=_view(self.reminders.current, finished=False),
            last_flow=_view(self.reminders.last, finished=True),
            next_reminder=(
                NextReminder(
                    next_up.id,
                    next_up.due_at,
                    self.reminders.start_time(next_up),
                    running=current is not None and current.reminder.id == next_up.id,
                    test=next_up.origin is ReminderOrigin.TEST,
                )
                if next_up
                else None
            ),
            events=tuple(list(self.bus.recent)[-40:]),
        )

    def latest_flow(self) -> FlowView | None:
        """The reminder flow running now, or else the last one. Reads no database, so the
        dashboard can ask on every page, every few seconds."""
        if self.reminders.current is not None:
            return _view(self.reminders.current, finished=False)
        return _view(self.reminders.last, finished=True)


def _view(flow: DueFlow | None, *, finished: bool) -> FlowView | None:
    if flow is None:
        return None
    history = flow.fsm.history
    steps = [(history[0].source.value, history[0].at, "")] if history else []
    steps += [(t.target.value, t.at, t.reason) for t in history]
    return FlowView(
        flow.reminder.id,
        flow.state.value,
        tuple(steps),
        finished,
        flow.delivered.value if flow.delivered else None,
        flow.problem,
        flow.planned.value if flow.planned else None,
        flow.answer.value if flow.answer else None,
    )
