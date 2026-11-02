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
| `flow.state` | The reminder flow moves to a new state. | `reason` |
| `flow.error` | A flow failed and went to the watch. | `error_type` |
| `owner.presence` | The watch was pinged. | `present` |
| `perception.voice` | A speech segment was identified. | `identity`, `similarity`, `plugin` |
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
| `owner.enrolled` | Face or voice enrolled. | `modality`, `samples`, `plugin` |
| `owner.enrolment_failed` | Face or voice enrolment stored nothing. | `modality`, `reason`, `pose` (face) or `samples` (voice) |
| `owner.face_pose` | One pose of a face enrolment, stored or not. | `pose`, `samples`, `frames`, `no_face`, `several` (faces), `unusable`, `reason` (commonest reason a frame went unused), `turned` and `tilt` (medians, see ADR 0011), `seconds` |
| `identity.calibrated` | A threshold was saved by calibration. | `modality`, `plugin`, `threshold`, `count` |
| `settings.changed` | Settings were saved. | `count` (settings changed) |

## What the log may hold

`EventBus.emit` accepts only these keys, with scalar values and strings of at most 80 characters,
and raises otherwise: `answer`, `channel`, `count`, `decision`, `direction`, `error_type`, `faces`,
`frames`, `identity`, `late_seconds`, `modality`, `mode`, `no_face`, `origin`, `plugin`,
`policy`, `pose`, `present`, `ready`, `reason`, `samples`, `seconds`, `sensitive`, `several`,
`similarity`, `threshold`, `tilt`, `turned`, `unusable`. Tests check that reminder
titles never appear in the log.

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

## Retention

`storage.event_log_retention_days` deletes older entries at start-up (0, the default, keeps
everything). `pasr reset --purge-log` deletes the whole log.
