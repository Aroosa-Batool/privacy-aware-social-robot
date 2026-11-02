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
from pasr.storage.repos import Feedback, Repositories
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
    assert db.migrate() == 2
    assert db.migrate() == 2


def test_a_database_from_before_the_feedback_gets_its_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from pasr.storage import db as storage

    old = Database.in_dir(tmp_path)
    monkeypatch.setattr(storage, "MIGRATIONS", storage.MIGRATIONS[:1])
    assert old.migrate() == 1
    monkeypatch.undo()
    assert old.migrate() == 2
    assert Repositories(old).feedback.all() == []


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


def log_run(repos: Repositories, session: str, reminder_id: int, *states: str, **logged) -> None:
    """A run's events: ``flow.started`` with what it ran with (unless it is from before that
    event existed), each state, and the delivery when ``channel`` is given."""
    bus = EventBus(SystemClock(), session, sinks=[repos.events.append])
    channel = logged.pop("channel", None)
    if logged:
        bus.emit(EventType.FLOW_STARTED, reminder_id=reminder_id, **logged)
    previous = "IDLE"
    for state in states:
        bus.emit(
            EventType.FLOW_STATE,
            reminder_id=reminder_id,
            state_from=previous,
            state_to=state,
            reason="",
        )
        previous = state
    if channel:
        bus.emit(EventType.REMINDER_DELIVERED, reminder_id=reminder_id, channel=channel)


def test_runs_are_put_together_from_their_events_newest_first(repos: Repositories):
    log_run(repos, "run-1", 7, "WAKING", "DONE", channel="spoken", speaker_model="ecapa")
    log_run(repos, "run-2", 7, "WAKING", "LISTENING", speaker_model="resemblyzer")  # again
    log_run(repos, "run-2", 8, "WAKING", "FAILED", channel="watch")  # logged before flow.started
    runs = repos.events.runs()
    assert [(r.session_id, r.reminder_id, r.state, r.channel) for r in runs] == [
        ("run-2", 8, "FAILED", "watch"),
        ("run-2", 7, "LISTENING", None),  # unfinished: the robot stopped, or is on it now
        ("run-1", 7, "DONE", "spoken"),
    ]
    assert [r.condition for r in runs] == [
        {},
        {"speaker_model": "resemblyzer"},
        {"speaker_model": "ecapa"},
    ]
    assert repos.events.run("run-1", 7) == runs[-1]
    assert repos.events.run("run-1", 8) is None


def test_feedback_keeps_its_run_and_a_second_verdict_replaces_the_first(repos: Repositories):
    log_run(repos, "run-1", 7, "WAKING", "DONE", channel="watch", speaker_model="ecapa")
    run = repos.events.run("run-1", 7)
    repos.feedback.save(run, worked=False, comment="it took my voice for someone's", now=NOW)
    later = NOW + timedelta(minutes=1)
    repos.feedback.save(run, worked=True, comment="", now=later)
    assert repos.feedback.all() == [Feedback(run, True, "", later)]
    assert repos.feedback.get("run-1", 7) == Feedback(run, True, "", later)
    assert repos.feedback.get("run-1", 8) is None
    repos.events.purge_older_than(later + timedelta(days=1))  # the log's retention
    assert repos.feedback.get("run-1", 7).run == run  # the feedback keeps its run


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
    log_run(repos, "t", 1, "WAKING", "DONE", channel="spoken", speaker_model="ecapa")
    repos.feedback.save(repos.events.run("t", 1), worked=True, comment="", now=NOW)
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
    assert repos.feedback.all()  # and the feedback on runs


def test_full_reset_deletes_owner_data(tmp_path: Path):
    db, repos, data_dir = populate(tmp_path)
    reset(db, data_dir, delete_owner=True, purge_log=True)
    assert repos.owner.get() is None
    assert repos.owner.embeddings(Biometric.VOICE) == []
    assert repos.reminders.all() == []
    assert repos.bystanders.all() == []
    assert repos.events.query() == []
    assert repos.feedback.all() == []


def test_runtime_lock_excludes_a_second_owner_in_the_same_process(tmp_path):
    from pasr.orchestration.lock import RuntimeBusyError, RuntimeLock

    with RuntimeLock(tmp_path):
        assert RuntimeLock(tmp_path).is_held_elsewhere()
        with pytest.raises(RuntimeBusyError), RuntimeLock(tmp_path):
            pass
    assert not RuntimeLock(tmp_path).is_held_elsewhere()
