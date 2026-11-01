-- Migration 1: initial schema. Times are ISO-8601 strings in UTC.

CREATE TABLE owner (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    display_name TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE owner_embedding (
    id         INTEGER PRIMARY KEY,
    owner_id   INTEGER NOT NULL DEFAULT 1 REFERENCES owner (id) ON DELETE CASCADE,
    modality   TEXT NOT NULL CHECK (modality IN ('face', 'voice')),
    model      TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    vector     BLOB NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE bystander (
    id            TEXT PRIMARY KEY,
    label         TEXT NOT NULL UNIQUE,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    seen_count    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE bystander_embedding (
    id           INTEGER PRIMARY KEY,
    bystander_id TEXT NOT NULL REFERENCES bystander (id) ON DELETE CASCADE,
    modality     TEXT NOT NULL CHECK (modality IN ('face', 'voice')),
    model        TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    vector       BLOB NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE reminder (
    id                 INTEGER PRIMARY KEY,
    title              TEXT NOT NULL,
    due_at             TEXT NOT NULL,
    sensitive          INTEGER NOT NULL CHECK (sensitive IN (0, 1)),
    sensitivity_score  REAL,
    sensitivity_source TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN
        ('scheduled', 'active', 'spoken', 'sent_to_watch', 'missed', 'cancelled')),
    origin             TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    delivered_at       TEXT
);
CREATE INDEX reminder_status_due ON reminder (status, due_at);

CREATE TABLE consent (
    id           INTEGER PRIMARY KEY,
    bystander_id TEXT NOT NULL REFERENCES bystander (id) ON DELETE CASCADE,
    allowed      INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    reminder_id  INTEGER REFERENCES reminder (id) ON DELETE SET NULL,
    source       TEXT NOT NULL,
    decided_at   TEXT NOT NULL,
    revoked_at   TEXT
);

-- Research log. Payloads are allow-listed labels and numbers; see pasr.orchestration.events.
CREATE TABLE event_log (
    id           INTEGER PRIMARY KEY,
    ts           TEXT NOT NULL,
    session_id   TEXT NOT NULL,
    type         TEXT NOT NULL,
    reminder_id  INTEGER,
    bystander_id TEXT,
    state_from   TEXT,
    state_to     TEXT,
    payload      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX event_log_ts ON event_log (ts);
