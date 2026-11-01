"""Data access without a running robot (CLI commands, dashboard pages while stopped).

A running runtime picks up changes made here on its next scheduler poll.
"""

from __future__ import annotations

from dataclasses import dataclass

from pasr.apps.reminder.service import ReminderService
from pasr.orchestration.clock import SystemClock
from pasr.orchestration.events import EventBus
from pasr.orchestration.lock import RuntimeLock
from pasr.paths import resolve
from pasr.perception.bundle import PerceptionBundle
from pasr.settings.schema import Settings
from pasr.storage.db import Database
from pasr.storage.repos import Repositories


@dataclass(slots=True)
class Offline:
    settings: Settings
    clock: SystemClock
    db: Database
    repos: Repositories
    bus: EventBus
    service: ReminderService

    @property
    def runtime_running(self) -> bool:
        return RuntimeLock(resolve(self.settings.storage.data_dir)).is_held_elsewhere()


def open_offline(settings: Settings, *, session_id: str = "offline") -> Offline:
    clock = SystemClock()
    db = Database.in_dir(resolve(settings.storage.data_dir))
    db.migrate()
    repos = Repositories(db)
    bus = EventBus(clock, session_id, sinks=[repos.events.append])
    service = ReminderService(
        repos=repos,
        perception=PerceptionBundle(
            settings.perception, models_dir=resolve(settings.storage.models_dir)
        ),
        clock=clock,
        bus=bus,
        settings=lambda: settings,
    )
    return Offline(settings, clock, db, repos, bus, service)
