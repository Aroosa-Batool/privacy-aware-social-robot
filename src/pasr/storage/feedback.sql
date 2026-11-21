-- Migration 2: the owner's feedback on reminder runs, for comparing models (ADR 0014).
-- A run is one reminder's flow in one session. It is copied from the event log (when it
-- started, how it ended, its flow.started condition) so the feedback outlives the log's
-- retention. The comment is free text, so it is kept here and never in the event log.

CREATE TABLE pipeline_feedback (
    session_id  TEXT NOT NULL,
    reminder_id INTEGER NOT NULL,
    started_at  TEXT NOT NULL,
    state       TEXT NOT NULL,
    channel     TEXT,
    condition   TEXT NOT NULL DEFAULT '{}',
    worked      INTEGER NOT NULL CHECK (worked IN (0, 1)),
    comment     TEXT NOT NULL DEFAULT '',
    rated_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, reminder_id)
);

CREATE INDEX event_log_run ON event_log (session_id, reminder_id);
