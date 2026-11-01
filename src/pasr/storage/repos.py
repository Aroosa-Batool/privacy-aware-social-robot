from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from pasr.domain.enums import Biometric, ConsentSource, ReminderOrigin, ReminderStatus
from pasr.domain.models import Bystander, Consent, Embedding, Owner, Reminder
from pasr.orchestration.events import Event
from pasr.storage.db import Database, from_db, maybe_from_db, to_db


def _blob(embedding: Embedding) -> bytes:
    return np.asarray(embedding.vector, dtype=np.float32).tobytes()


def _embedding(row: sqlite3.Row) -> Embedding:
    vector = np.frombuffer(row["vector"], dtype=np.float32)
    if vector.shape[0] != row["dim"]:
        raise ValueError("corrupt embedding row")
    return Embedding(vector=vector.copy(), model=row["model"])


class OwnerRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self) -> Owner | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM owner WHERE id = 1").fetchone()
        if row is None:
            return None
        return Owner(row["display_name"], from_db(row["created_at"]), from_db(row["updated_at"]))

    def save(self, display_name: str, now: datetime) -> Owner:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO owner (id, display_name, created_at, updated_at) VALUES (1, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET display_name = excluded.display_name,"
                " updated_at = excluded.updated_at",
                (display_name, to_db(now), to_db(now)),
            )
        owner = self.get()
        assert owner is not None
        return owner

    def replace_embeddings(
        self, modality: Biometric, embeddings: Iterable[Embedding], now: datetime
    ) -> int:
        rows = [(modality.value, e.model, e.dim, _blob(e), to_db(now)) for e in embeddings]
        with self.db.connect() as conn:
            conn.execute("DELETE FROM owner_embedding WHERE modality = ?", (modality.value,))
            conn.executemany(
                "INSERT INTO owner_embedding (modality, model, dim, vector, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def embeddings(self, modality: Biometric) -> list[Embedding]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT model, dim, vector FROM owner_embedding WHERE modality = ? ORDER BY id",
                (modality.value,),
            ).fetchall()
        return [_embedding(r) for r in rows]

    def delete_embeddings(self, modality: Biometric) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM owner_embedding WHERE modality = ?", (modality.value,)
            )
        return cursor.rowcount

    def enrollment(self) -> dict[Biometric, tuple[int, list[str]]]:
        """Sample count and model names per modality."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT modality, model, COUNT(*) AS n FROM owner_embedding"
                " GROUP BY modality, model"
            ).fetchall()
        result: dict[Biometric, tuple[int, list[str]]] = {}
        for row in rows:
            count, models = result.get(Biometric(row["modality"]), (0, []))
            result[Biometric(row["modality"])] = (count + row["n"], [*models, row["model"]])
        return result


class BystanderRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self, embeddings: Iterable[Embedding], modality: Biometric, now: datetime
    ) -> Bystander:
        bystander_id = uuid.uuid4().hex[:12]
        with self.db.connect() as conn:
            number = conn.execute("SELECT COUNT(*) FROM bystander").fetchone()[0] + 1
            while conn.execute(
                "SELECT 1 FROM bystander WHERE label = ?", (f"B-{number:03d}",)
            ).fetchone():
                number += 1
            conn.execute(
                "INSERT INTO bystander (id, label, first_seen_at, last_seen_at, seen_count)"
                " VALUES (?, ?, ?, ?, 1)",
                (bystander_id, f"B-{number:03d}", to_db(now), to_db(now)),
            )
            conn.executemany(
                "INSERT INTO bystander_embedding"
                " (bystander_id, modality, model, dim, vector, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (bystander_id, modality.value, e.model, e.dim, _blob(e), to_db(now))
                    for e in embeddings
                ],
            )
        created = self.get(bystander_id)
        assert created is not None
        return created

    def get(self, bystander_id: str) -> Bystander | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM bystander WHERE id = ?", (bystander_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def all(self) -> list[Bystander]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM bystander ORDER BY label").fetchall()
        return [self._from_row(r) for r in rows]

    def embeddings(self, modality: Biometric) -> dict[str, list[Embedding]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT bystander_id, model, dim, vector FROM bystander_embedding"
                " WHERE modality = ? ORDER BY id",
                (modality.value,),
            ).fetchall()
        result: dict[str, list[Embedding]] = defaultdict(list)
        for row in rows:
            result[row["bystander_id"]].append(_embedding(row))
        return dict(result)

    def modalities(self) -> dict[str, list[Biometric]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT bystander_id, modality FROM bystander_embedding"
            ).fetchall()
        result: dict[str, list[Biometric]] = defaultdict(list)
        for row in rows:
            result[row["bystander_id"]].append(Biometric(row["modality"]))
        return dict(result)

    def mark_seen(self, bystander_id: str, now: datetime) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE bystander SET last_seen_at = ?, seen_count = seen_count + 1 WHERE id = ?",
                (to_db(now), bystander_id),
            )

    def delete(self, bystander_id: str) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM bystander WHERE id = ?", (bystander_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Bystander:
        return Bystander(
            id=row["id"],
            label=row["label"],
            first_seen_at=from_db(row["first_seen_at"]),
            last_seen_at=from_db(row["last_seen_at"]),
            seen_count=row["seen_count"],
        )


class ConsentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        bystander_id: str,
        allowed: bool,
        *,
        source: ConsentSource,
        now: datetime,
        reminder_id: int | None = None,
    ) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO consent (bystander_id, allowed, reminder_id, source, decided_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (bystander_id, int(allowed), reminder_id, source.value, to_db(now)),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def effective(self, bystander_ids: Iterable[str]) -> dict[str, bool]:
        """Latest non-revoked decision per bystander."""
        ids = list(bystander_ids)
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT bystander_id, allowed FROM consent WHERE revoked_at IS NULL"
                f" AND bystander_id IN ({marks}) ORDER BY id",
                ids,
            ).fetchall()
        return {row["bystander_id"]: bool(row["allowed"]) for row in rows}

    def all(self, *, include_revoked: bool = True) -> list[Consent]:
        query = "SELECT * FROM consent"
        if not include_revoked:
            query += " WHERE revoked_at IS NULL"
        with self.db.connect() as conn:
            rows = conn.execute(query + " ORDER BY id DESC").fetchall()
        return [
            Consent(
                id=row["id"],
                bystander_id=row["bystander_id"],
                allowed=bool(row["allowed"]),
                reminder_id=row["reminder_id"],
                source=ConsentSource(row["source"]),
                decided_at=from_db(row["decided_at"]),
                revoked_at=maybe_from_db(row["revoked_at"]),
            )
            for row in rows
        ]

    def revoke_last(self, now: datetime, *, hard: bool = False) -> Consent | None:
        """Forget the most recent remembered decision (soft: keep it, marked revoked)."""
        active = self.all(include_revoked=False)
        if not active:
            return None
        last = active[0]
        with self.db.connect() as conn:
            if hard:
                conn.execute("DELETE FROM consent WHERE id = ?", (last.id,))
            else:
                conn.execute(
                    "UPDATE consent SET revoked_at = ? WHERE id = ?", (to_db(now), last.id)
                )
        return last


class ReminderRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        *,
        title: str,
        due_at: datetime,
        sensitive: bool,
        sensitivity_score: float | None,
        sensitivity_source: str,
        origin: ReminderOrigin,
        now: datetime,
    ) -> Reminder:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reminder (title, due_at, sensitive, sensitivity_score,"
                " sensitivity_source, status, origin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    title,
                    to_db(due_at),
                    int(sensitive),
                    sensitivity_score,
                    sensitivity_source,
                    ReminderStatus.SCHEDULED.value,
                    origin.value,
                    to_db(now),
                ),
            )
        assert cursor.lastrowid is not None
        reminder = self.get(cursor.lastrowid)
        assert reminder is not None
        return reminder

    def get(self, reminder_id: int) -> Reminder | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM reminder WHERE id = ?", (reminder_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def all(self, statuses: Iterable[ReminderStatus] | None = None) -> list[Reminder]:
        query, params = "SELECT * FROM reminder", []
        if statuses is not None:
            wanted = [s.value for s in statuses]
            query += f" WHERE status IN ({','.join('?' * len(wanted))})"
            params = wanted
        with self.db.connect() as conn:
            rows = conn.execute(query + " ORDER BY due_at, id", params).fetchall()
        return [self._from_row(r) for r in rows]

    def set_status(
        self, reminder_id: int, status: ReminderStatus, *, delivered_at: datetime | None = None
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE reminder SET status = ?, delivered_at = ? WHERE id = ?",
                (status.value, None if delivered_at is None else to_db(delivered_at), reminder_id),
            )

    def recover_interrupted(self) -> int:
        """Flows interrupted by a crash or shutdown run again."""
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE reminder SET status = 'scheduled' WHERE status = 'active'"
            )
        return cursor.rowcount

    def delete(self, reminder_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM reminder WHERE id = ?", (reminder_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=row["id"],
            title=row["title"],
            due_at=from_db(row["due_at"]),
            sensitive=bool(row["sensitive"]),
            sensitivity_score=row["sensitivity_score"],
            sensitivity_source=row["sensitivity_source"],
            status=ReminderStatus(row["status"]),
            origin=ReminderOrigin(row["origin"]),
            created_at=from_db(row["created_at"]),
            delivered_at=maybe_from_db(row["delivered_at"]),
        )


@dataclass(frozen=True, slots=True)
class LoggedEvent:
    id: int
    ts: datetime
    session_id: str
    type: str
    reminder_id: int | None
    bystander_id: str | None
    state_from: str | None
    state_to: str | None
    payload: Mapping[str, object]


class EventRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def append(self, event: Event) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO event_log (ts, session_id, type, reminder_id, bystander_id,"
                " state_from, state_to, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    to_db(event.ts),
                    event.session_id,
                    event.type.value,
                    event.reminder_id,
                    event.bystander_id,
                    event.state_from,
                    event.state_to,
                    json.dumps(dict(event.data)),
                ),
            )

    def query(
        self,
        *,
        limit: int = 500,
        types: Iterable[str] | None = None,
        session_id: str | None = None,
    ) -> list[LoggedEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if types:
            wanted = list(types)
            clauses.append(f"type IN ({','.join('?' * len(wanted))})")
            params.extend(wanted)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM event_log{where} ORDER BY id DESC LIMIT ?", [*params, limit]
            ).fetchall()
        return [
            LoggedEvent(
                id=row["id"],
                ts=from_db(row["ts"]),
                session_id=row["session_id"],
                type=row["type"],
                reminder_id=row["reminder_id"],
                bystander_id=row["bystander_id"],
                state_from=row["state_from"],
                state_to=row["state_to"],
                payload=json.loads(row["payload"]),
            )
            for row in rows
        ]

    def sessions(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM event_log GROUP BY session_id ORDER BY MAX(id) DESC"
            ).fetchall()
        return [row["session_id"] for row in rows]

    def purge_older_than(self, cutoff: datetime) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM event_log WHERE ts < ?", (to_db(cutoff),))
        return cursor.rowcount


class Repositories:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.owner = OwnerRepository(db)
        self.bystanders = BystanderRepository(db)
        self.consents = ConsentRepository(db)
        self.reminders = ReminderRepository(db)
        self.events = EventRepository(db)
