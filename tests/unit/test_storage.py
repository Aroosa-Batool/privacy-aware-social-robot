from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from pasr.domain.enums import Biometric, ConsentSource, ReminderOrigin, ReminderStatus
from pasr.domain.models import Embedding
from pasr.orchestration.clock import SystemClock
from pasr.orchestration.events import EventBus, EventType
from pasr.settings.loader import read_overrides, update_overrides
from pasr.storage.db import Database
from pasr.storage.repos import Repositories
from pasr.storage.reset import reset

NOW = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def vec(*values):
    return Embedding.of(values, "test-model")


def add_reminder(repos, title="Dentist", status=None):
    reminder = repos.reminders.add(
        title=title,
        due_at=NOW + timedelta(hours=1),
        sensitive=True,
        sensitivity_score=1.0,
        sensitivity_source="keyword",
        origin=ReminderOrigin.CLI,
        now=NOW,
    )
    if status:
        repos.reminders.set_status(reminder.id, status)
    return reminder


def test_migrations_are_idempotent(tmp_path: Path):
    db = Database.in_dir(tmp_path)
    assert db.migrate() == 1
    assert db.migrate() == 1


def test_owner_and_embeddings_round_trip(repos: Repositories):
    assert repos.owner.get() is None
    repos.owner.save("Aroosa", NOW)
    repos.owner.save("Aroosa B", NOW)
    assert repos.owner.get().display_name == "Aroosa B"
    repos.owner.replace_embeddings(Biometric.FACE, [vec(1, 0), vec(0, 1)], NOW)
    stored = repos.owner.embeddings(Biometric.FACE)
    assert len(stored) == 2
    assert np.allclose(stored[0].vector, [1, 0])
    assert stored[0].model == "test-model"
    assert repos.owner.enrollment() == {Biometric.FACE: (2, ["test-model"])}
    repos.owner.replace_embeddings(Biometric.FACE, [vec(1, 1)], NOW)
    assert len(repos.owner.embeddings(Biometric.FACE)) == 1


def test_timestamps_are_timezone_aware(repos: Repositories):
    reminder = add_reminder(repos)
    loaded = repos.reminders.get(reminder.id)
    assert loaded.due_at == NOW + timedelta(hours=1)
    assert loaded.due_at.tzinfo is not None


def test_bystanders_get_sequential_labels_and_cascade(repos: Repositories):
    first = repos.bystanders.create([vec(1, 0)], Biometric.VOICE, NOW)
    second = repos.bystanders.create([vec(0, 1)], Biometric.FACE, NOW)
    assert (first.label, second.label) == ("B-001", "B-002")
    repos.bystanders.mark_seen(first.id, NOW + timedelta(minutes=5))
    assert repos.bystanders.get(first.id).seen_count == 2
    assert set(repos.bystanders.embeddings(Biometric.VOICE)) == {first.id}
    repos.consents.record(first.id, True, source=ConsentSource.WATCH, now=NOW)
    assert repos.bystanders.delete(first.id)
    assert repos.bystanders.embeddings(Biometric.VOICE) == {}
    assert repos.consents.all() == []


def test_effective_consent_and_delete_last(repos: Repositories):
    b = repos.bystanders.create([vec(1, 0)], Biometric.VOICE, NOW).id
    repos.consents.record(b, False, source=ConsentSource.WATCH, now=NOW)
    repos.consents.record(b, True, source=ConsentSource.WATCH, now=NOW + timedelta(minutes=1))
    assert repos.consents.effective([b]) == {b: True}

    revoked = repos.consents.revoke_last(NOW)
    assert revoked is not None and revoked.allowed
    assert repos.consents.effective([b]) == {b: False}  # the earlier answer applies again
    assert len(repos.consents.all()) == 2  # soft revoke keeps an audit trail

    repos.consents.revoke_last(NOW, hard=True)
    assert repos.consents.effective([b]) == {}
    assert len(repos.consents.all()) == 1
    assert repos.consents.revoke_last(NOW) is None


def test_interrupted_flows_are_rescheduled(repos: Repositories):
    reminder = add_reminder(repos, status=ReminderStatus.ACTIVE)
    assert repos.reminders.recover_interrupted() == 1
    assert repos.reminders.get(reminder.id).status is ReminderStatus.SCHEDULED
    assert repos.reminders.all([ReminderStatus.SPOKEN]) == []


def populate(tmp_path: Path) -> tuple[Database, Repositories, Path]:
    data_dir = tmp_path / "data"
    db = Database.in_dir(data_dir)
    db.migrate()
    repos = Repositories(db)
    repos.owner.save("Owner", NOW)
    repos.owner.replace_embeddings(Biometric.VOICE, [vec(1, 0)], NOW)
    add_reminder(repos)
    b = repos.bystanders.create([vec(0, 1)], Biometric.VOICE, NOW).id
    repos.consents.record(b, True, source=ConsentSource.WATCH, now=NOW)
    EventBus(SystemClock(), "t", sinks=[repos.events.append]).emit(EventType.RUNTIME_STARTED)
    update_overrides(data_dir, {"privacy": {"disclosure_policy": "always_disclose"}})
    return db, repos, data_dir


def test_partial_reset_keeps_owner_and_reminders(tmp_path: Path):
    db, repos, data_dir = populate(tmp_path)
    summary = reset(db, data_dir, delete_owner=False)
    assert summary.settings_cleared and read_overrides(data_dir) == {}
    assert repos.bystanders.all() == [] and repos.consents.all() == []
    assert repos.owner.get() is not None
    assert repos.owner.embeddings(Biometric.VOICE)
    assert len(repos.reminders.all()) == 1
    assert repos.events.query()  # the research log is kept


def test_full_reset_deletes_owner_data(tmp_path: Path):
    db, repos, data_dir = populate(tmp_path)
    reset(db, data_dir, delete_owner=True, purge_log=True)
    assert repos.owner.get() is None
    assert repos.owner.embeddings(Biometric.VOICE) == []
    assert repos.reminders.all() == []
    assert repos.bystanders.all() == []
    assert repos.events.query() == []


def test_runtime_lock_excludes_a_second_owner_in_the_same_process(tmp_path):
    from pasr.orchestration.lock import RuntimeBusyError, RuntimeLock

    with RuntimeLock(tmp_path):
        assert RuntimeLock(tmp_path).is_held_elsewhere()
        with pytest.raises(RuntimeBusyError), RuntimeLock(tmp_path):
            pass
    assert not RuntimeLock(tmp_path).is_held_elsewhere()
