---
title: Event log and metrics
description: The research log records what the robot did and why, as labels and numbers. Every event type, the keys its data may hold, and how to get it out.
---

The runtime publishes typed events to an in-process bus that feeds the dashboard and a SQLite
table, `event_log`, with the columns `ts`, `session_id`, `type`, `reminder_id`, `bystander_id`,
`state_from`, `state_to` and `payload` (a small JSON object).

## Event types

| Type | When | Typical data |
|---|---|---|
| `runtime.started` · `runtime.stopped` | The robot starts or stops (a new session). | |
| `flow.started` | A reminder's flow starts, before its first step (ADR 0014). | `speaker_model`, `vad_model`, `face_model`, `sensitivity_model` (the model that judged the reminder, or `user`), `voice_threshold`, `face_threshold`, `mode` (detection), `policy`, `sensitive`, `origin` |
| `flow.state` | The reminder flow moves to a new state. | `reason` |
| `flow.error` | A flow failed and went to the watch. | `error_type` |
| `owner.presence` | The watch was pinged. | `present` |
| `perception.voice` | A speech segment was identified. | `identity`, `similarity`, `plugin`, `seconds` (segment length), `level` (loudness, dBFS) |
| `perception.voice_pooled` | A voice other than the owner's had enough speech to judge, and was judged on all of it (ADR 0013). | `identity` (owner / someone_else), `similarity` (of the averaged segments), `samples` (segments), `seconds` (their speech) |
| `perception.face` | A face was identified during a scan. | `identity`, `similarity`, `plugin` |
| `perception.face_studied` | The robot looked closer at a face it did not recognise at once. | `direction`, `identity` (decided from the averaged views), `ready` (seen in full view), `count` (head moves), `frames`, `seconds` |
| `perception.scan` | A room scan ended. | `count` (full sweeps), `frames`, `seconds`, `reason` (found someone / found only people allowed before / found no one) |
| `consent.requested` | The watch prompt was shown. | `count` (people detected) |
| `consent.answered` | The owner answered, or the prompt timed out. | `answer` |
| `consent.revoked` | A remembered answer was withdrawn. | |
| `bystander.enrolled` | A bystander was remembered. | `modality` |
| `reminder.created` | A reminder was added. | `sensitive`, `origin` |
| `reminder.delivered` | Said or shown on the watch. | `channel`, `late_seconds` |
| `reminder.missed` | Found too late, or the watch was unreachable at the due time. | `reason` |
| `owner.enrolled` | Face or voice enrolled. | `modality`, `samples`, `plugin`; voice: `seconds` (speech), `unusable` (samples left out), `similarity` (median fit of each sample to the others) |
| `owner.enrolment_failed` | Face or voice enrolment stored nothing. | `modality`, `reason`, `pose` (face) or `samples` and `seconds` (voice) |
| `owner.face_pose` | One pose of a face enrolment, stored or not. | `pose`, `samples`, `frames`, `no_face`, `several` (faces), `unusable`, `reason` (commonest reason a frame went unused), `turned` and `tilt` (medians, see ADR 0011), `seconds` |
| `identity.calibrated` | A threshold was saved by calibration. | `modality`, `plugin`, `threshold`, `count` |
| `settings.changed` | Settings were saved. | `count` (settings changed) |

## What the log may hold

`EventBus.emit` accepts only these keys, with scalar values and strings of at most 80 characters,
and raises otherwise: `answer`, `channel`, `count`, `decision`, `direction`, `error_type`,
`face_model`, `face_threshold`, `faces`, `frames`, `identity`, `late_seconds`, `level`,
`modality`, `mode`, `no_face`, `origin`, `plugin`, `policy`, `pose`, `present`, `ready`, `reason`,
`samples`, `seconds`, `sensitive`, `sensitivity_model`, `several`, `similarity`, `speaker_model`,
`threshold`, `tilt`, `turned`, `unusable`, `vad_model`, `voice_threshold`. Tests check that
reminder titles never appear in the log.

## Pipeline feedback

Whether a run worked is something only the owner can tell, so the owner marks it: on Home under
the pipeline once a run has ended, or for any logged run on the [Events](/dashboard/events) page.
A **run** is one reminder's flow in one session. Each verdict (worked well or not, and with a
thumbs down an optional comment on what went wrong) is stored in the `pipeline_feedback` table
with a copy of the run: when it started, its last state, where the reminder went, and its
`flow.started` condition. The comment is free text, so it never enters the event log
([ADR 0014](/decisions/0014-pipeline-feedback)).

**Download feedback CSV** on the Events page gives one row per rated run, with a column per
model, ready to compare:

```python
feedback = pd.read_csv("pasr-pipeline-feedback.csv")
print(feedback.groupby(["speaker_model", "face_model"]).worked.agg(["mean", "count"]))
print(feedback[~feedback.worked][["speaker_model", "comment"]])  # what went wrong, per model
```

A run's own events share its `session_id` and `reminder_id`, so the scores behind a verdict are
one join away.

## Get it out

Download CSV or JSON Lines on the [Events](/dashboard/events) page, filtered by session and type,
or read the database directly:

```python
import json, sqlite3
import pandas as pd

con = sqlite3.connect("data/pasr.db")
events = pd.read_sql("SELECT * FROM event_log", con)
voice = events[events.type == "perception.voice"]
voice = voice.join(voice.payload.apply(json.loads).apply(pd.Series))
print(voice.groupby("identity").similarity.describe())
```

## Measures it supports

| Measure | From |
|---|---|
| How often the robot spoke, asked, or sent to the watch | `reminder.delivered` (`channel`), `flow.state` |
| False alarms and misses of bystander detection | `perception.voice` / `perception.face` (`identity`, `similarity`) against your ground truth |
| How often it failed closed, and why | `flow.error` (`error_type`) |
| Owner response rate and time | `consent.requested` → `consent.answered` |
| Delivery punctuality | `reminder.delivered` (`late_seconds`) |
| Cost of looking closer and following | `perception.face_studied` (`count`, `frames`, `seconds`) |
| How much of the room each scan covered | `perception.scan` (`count`, `seconds`) |
| How often each model's runs worked, and what went wrong | Pipeline feedback, by its model columns |
| Which models and thresholds a run used | `flow.started` |

## Retention

`storage.event_log_retention_days` deletes older entries at start-up (0, the default, keeps
everything); the pipeline feedback keeps its copy of each run. `pasr reset --purge-log` deletes
the whole log and the feedback.
