---
title: Privacy model
description: The robot exists to protect the owner's private information from people nearby, so it must handle everyone's data, the owner's and the bystanders', carefully itself. What it processes, what it keeps, and how each guarantee is enforced.
---

A robot that recorded the room to protect a reminder would create a bigger privacy problem than
the one it solves. This page lists what the robot processes, what it keeps and for how long, and
how each guarantee is enforced in code and tests, so you can check the claims rather than take
them on trust. The same content lives in the repository as `docs/PRIVACY.md`.

## What is processed, and what is kept

| Data | Comes from | Kept? | How long |
|---|---|---|---|
| Camera frames | Head camera, only while enrolling, scanning or calibrating | **Never**, in memory only | Dropped after embedding |
| Audio | Laptop microphone, only while listening, enrolling or calibrating | **Never**, in memory only | Dropped after embedding or transcription |
| Live view (off by default) | Frames, levels and labels of the listening, scanning, enrolment and calibration steps, in a window on the laptop | **Never**, in memory and an OS pipe only | The latest frame while its step lasts; a few seconds of levels and the last six labels |
| Researcher WAV files and image folders | `microphone.source: wav`, `camera.source: images` | Read only; never copied or written | |
| Calibration scores | `pasr calibrate` | **Never**; only the chosen threshold is saved | |
| The robot's own speech file | Written by the `ohbot` library while it speaks (contains the title) | Deleted after every utterance; lives in `.ohbot/`, never in `data/` | Seconds |
| Speech transcripts | Speech-to-text, when setting a reminder by voice | **Never** | Used only to parse the reminder |
| Owner face and voice embeddings | Enrolment | Yes | Until re-enrolled, deleted or a full reset |
| Bystander embeddings | Detection, **only** with *ask once* **and** an answer from the owner | Yes, at most 5 per person | Until forgotten or reset |
| Consent answers | The owner, on the watch | Yes, revocable | Until deleted or reset |
| Reminder titles, times, sensitivity | The owner | Yes | Until deleted or a full reset |
| Research event log | The runtime | Yes, **labels and numbers only** | Until purged |
| Pipeline feedback | The owner, rating a run on Home or Events | Yes: worked or not, an optional comment in the owner's words, the run's models; **never in the event log** | Until purged with the log |

Bystanders are anonymous labels (`B-001`). The robot never knows their names.

## Guarantees, and how they are enforced

:::cards 2
eye-off | [No raw media on disk](#no-raw-media-on-disk) | A lint rule, database checks after every scenario test, `.gitignore` and a pre-commit size limit.
watch | [Nothing sensed while the owner is away](#owner-away) | The presence ping comes before any sensor, and again before speaking.
shield-check | [Uncertainty never means speaking](#fail-closed) | Every error and every unanswered prompt goes to the watch.
database | [Deletion really deletes](#deletion) | `secure_delete`, WAL checkpoints, cascades.
:::

### No raw media on disk

Recordings would be the most sensitive data the system could hold, so it never writes any
([ADR 0002](/decisions/0002-embeddings-only)). Frames and audio exist only as in-memory `Frame`
and `AudioChunk` objects. A ruff rule (TID251) bans `cv2.imwrite`, `cv2.VideoWriter`, `soundfile.write`, `scipy.io.wavfile.write`, `numpy.save` and
`numpy.savez` in `src/`, so code that tried to save media would fail the checks. After every scenario test, the suite checks that the only binary data in
the database is float32 vectors of the declared size and that the data folder holds nothing but
the database. `.gitignore` and a 500 KB pre-commit limit keep media out of git.

### Owner away {#owner-away}

If the owner is not in the room, there is nothing to protect, and listening or looking around
would only capture other people. So every reminder flow first pings the owner's watch
(`CHECKING_PRESENCE`). Without an answer from
the consent app the flow goes to `OWNER_AWAY` and straight to watch delivery: the microphone and
camera are never opened and nothing is said. The watch is pinged again right before speaking.
Scenario tests `owner_away_never_senses` and `owner_leaves_before_due` check it.
([ADR 0007](/decisions/0007-owner-presence-first))

### The camera only when allowed and needed

The camera is opened only for enrolment and the scan step. It is closed in a `finally` block, so
an error cannot leave it running, and it runs in a helper process that releases it if the robot's process dies. With detection *audio only* the flow never
reaches the scan (`audio_only_never_uses_camera`); with *camera only* it never opens the
microphone to look for bystanders (`camera_only_never_listens`). The scan keeps the camera on
until the due time (2 minutes when the reminder is on time) unless it finds someone sooner, and
logs only how many sweeps it made and whether it found someone; a closer look at one face logs
only the direction, who it turned out to be, whether the face came into full view, the number of
head moves and frames, and the seconds.

### Following never makes speaking more likely

Following a face is meant to get a clearer view of it, never to lose it. A followed face is
always compared: if it never comes into full view, or is lost, its best view so far is compared
instead, so it still counts as a bystander unless it clearly matches the owner.

### The live view shows, never stores

The live view is off by default. Only the latest frame of the current step is kept in memory and dropped when the
step ends; a separate window process receives it through a pipe. It never shows a reminder title
and nothing while the owner is away. It does show bystanders' faces, so it is for development or
for sessions whose participants agreed to it.

### The event log holds no personal content

The event log exists for research, and research needs numbers, not people's details.
`EventBus.emit` accepts only allow-listed keys with short scalar values and raises an error for
anything else, so a careless log call cannot leak personal content.
Tests check that reminder titles never appear in the log.

### Uncertainty never leads to speaking aloud {#fail-closed}

Any error (missing enrolment, a model mismatch, a crashed plugin, an unreachable device) moves the
flow to `FAILED` and sends the reminder to the watch. An unanswered consent prompt counts as
*no*, and nothing is remembered from it. The price is that a reminder is occasionally sent to
the watch when it could safely have been spoken. ([ADR 0003](/decisions/0003-fail-closed))

### Bystander data is minimal

Bystander embeddings are stored only when the owner gives a Yes or No under the *ask once*
policy, because only then is there something to remember.

### Sensitive titles are not repeated

After a reminder is set by voice, the robot's spoken confirmation leaves out a sensitive title,
so the confirmation does not disclose what the reminder itself would not.

### Deletion really deletes {#deletion}

SQLite `secure_delete` overwrites deleted rows instead of only marking them free. A reset
checkpoints the write-ahead log, so deleted data does not linger there. Forgetting
a bystander cascades to their embeddings and consent answers.

### Embeddings from different models are never compared

Embeddings from different models are not comparable, and comparing them would give meaningless
scores. So each embedding stores its model name. Matching against another model raises, which fails closed,
and the dashboard asks for re-enrolment.

### No network except one deliberate download

`pasr models download` (or a plugin's first use) fetches weights into `models/`; nothing else opens
a connection. Silero and Resemblyzer weights ship inside their packages.

### Only what is needed is inferred

InsightFace is loaded with `allowed_modules=["detection", "recognition"]`: its age and gender
model is never loaded, so the robot cannot guess those attributes.

### Calibration stores nothing about other people

Calibration needs samples of other people to find a good threshold, but it does not need to keep
them. Their samples are scored against the owner and dropped; only numbers come back, and the
log records only the modality, plugin and threshold.

## Reset

| | Bystanders and embeddings | Consent answers | Preferences | Owner name, face, voice | Reminders | Event log and pipeline feedback |
|---|---|---|---|---|---|---|
| Reset, keep owner | deleted | deleted | deleted | kept | kept | kept |
| Reset, delete owner | deleted | deleted | deleted | deleted | deleted | kept |
| `--purge-log` | | | | | | deleted |

*Delete last consent* takes back the newest remembered answer. By default it keeps the answer
marked as revoked, for the audit trail; with `--hard` it deletes it outright.
