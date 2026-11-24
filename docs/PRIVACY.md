# Privacy model

The robot exists to protect the owner's private information from people nearby. That only works
if it handles everyone's data (the owner's and the bystanders') carefully itself: a robot that
recorded the room to protect a reminder would create a bigger privacy problem than the one it
solves. This document lists what the robot processes, what it keeps and for how long, and how each
privacy guarantee is enforced in code and tests, so you can check the claims rather than take them
on trust.

## What is processed, and what is kept

| Data | Where it comes from | Kept? | How long |
|---|---|---|---|
| Camera frames | Head camera, only while enrolling, scanning or calibrating | **Never**; in memory only | Dropped after embedding |
| Audio | Laptop microphone, only while listening, enrolling or calibrating | **Never**; in memory only | Dropped after embedding / transcription |
| Live view (off by default, `live_view.enabled`) | The frames, audio levels and match labels of the listening, scanning, enrolment and calibration steps, shown in a window on the laptop | **Never**; in memory and an OS pipe only | The latest frame only while its step lasts (no last frame stays on screen); a few seconds of levels and the last six labels until the next step, until the live view is switched off, or until the robot stops |
| Researcher-supplied WAV files / image folders | `hardware.microphone.source: wav`, `hardware.camera.source: images` | Read only; the robot never copies or writes them | (not applicable) |
| Calibration scores | `pasr calibrate` | **Never** (held in memory for the session); only the chosen threshold is saved to `settings.json` | (not applicable) |
| The robot's own speech (`ohbotspeech.wav`) | Written by the `ohbot` library when it speaks (contains the reminder title) | Deleted after every utterance; lives in `.ohbot/`, never in `data/` | Seconds |
| Speech transcripts | Speech-to-text, when setting a reminder by voice | **Never** | Used only to parse the reminder |
| Owner face / voice embeddings | Enrolment | Yes (`owner_embedding`) | Until re-enrolled, deleted or a full reset |
| Bystander embeddings | Detection, **only** with the ask-once policy **and** an answer from the owner | Yes (`bystander_embedding`, ≤ 5 per person) | Until forgotten or reset |
| Consent answers | Owner on the watch | Yes (`consent`), revocable | Until deleted or reset |
| Reminder titles, times, sensitivity | Owner | Yes (`reminder`) | Until deleted or a full reset |
| Research event log | Runtime | Yes (`event_log`), **labels and numbers only** | Until purged (`storage.event_log_retention_days`) |
| Pipeline feedback | Owner, rating a run on Home or Events | Yes (`pipeline_feedback`): worked or not, an optional free-text comment, a copy of the run and its models; **never in the event log** (ADR 0014) | Until purged with the log (`--purge-log`) |

Bystanders are only ever anonymous labels (`B-001`). The robot never knows their names.

## Guarantees and how they are enforced

| Guarantee | Enforced by |
|---|---|
| [No raw media on disk](#no-raw-media-on-disk) | A lint rule, database checks after every scenario test, `.gitignore`, a pre-commit size limit |
| [Nothing is sensed or said while the owner is away](#nothing-is-sensed-or-said-while-the-owner-is-away) | The presence ping before any sensor; scenario tests |
| [The camera is used only when allowed and needed](#the-camera-is-used-only-when-allowed-and-needed) | `finally` blocks, a helper process, scenario tests |
| [Following never makes speaking more likely](#following-never-makes-speaking-more-likely) | Always comparing the best view; component tests |
| [The live view shows, never stores](#the-live-view-shows-never-stores) | In-memory feed, pipe to a window process; component tests |
| [The event log holds no personal content](#the-event-log-holds-no-personal-content) | An allow-list in `EventBus.emit`; tests |
| [Uncertainty never leads to speaking aloud](#uncertainty-never-leads-to-speaking-aloud) | The `FAILED` state; unanswered prompts count as *no* |
| [Bystander data is minimal](#bystander-data-is-minimal) | Storing embeddings only with an owner answer |
| [Sensitive titles are not repeated](#sensitive-titles-are-not-repeated) | The voice confirmation leaves them out |
| [Deletion really deletes](#deletion-really-deletes) | SQLite `secure_delete`, WAL checkpoint, cascades |
| [Embeddings from different models are never compared](#embeddings-from-different-models-are-never-compared) | A model name on every embedding |
| [No network use except one deliberate model download](#no-network-use-except-one-deliberate-model-download) | `pasr models download` is the only connection |
| [Only what is needed is inferred](#only-what-is-needed-is-inferred) | InsightFace `allowed_modules` |
| [Calibration stores nothing about other people](#calibration-stores-nothing-about-other-people) | `CalibrationService` returns numbers only |

### No raw media on disk

Recordings would be the most sensitive data the system could hold, so it never writes any
(ADR 0002). Frames and audio exist only as in-memory `Frame` / `AudioChunk` objects. A lint rule
(`ruff` TID251) bans `cv2.imwrite`, `cv2.VideoWriter`, `soundfile.write`, `scipy.io.wavfile.write`
and `numpy.save` in `src/`, so code that tried to save media would fail the checks. After every
scenario test, the test suite checks that the only binary data in the database is float32 vectors
of the declared size, and that the data directory holds nothing but the database. `.gitignore` and
a pre-commit size limit keep media out of git.

### Nothing is sensed or said while the owner is away

If the owner is not in the room, there is nothing to protect, and listening or looking around would
only capture other people. So every reminder flow first pings the owner's watch over Bluetooth
(`CHECKING_PRESENCE`). If the watch does not answer with the consent app loaded, the flow goes to
`OWNER_AWAY` and straight to watch delivery: the microphone and camera are never opened and
nothing is said. The watch is pinged again right before the robot speaks. The scenario tests
`owner_away_never_senses` and `owner_leaves_before_due` check that neither sensor is opened and
nothing is spoken. See ADR 0007.

### The camera is used only when allowed and needed

The camera is opened only for enrolment and for the scan step, and it is closed in a `finally`
block so an error cannot leave it running.

- **Scan.** The camera stays on until the due time (2 minutes when the reminder is on time),
  unless the robot recognises someone sooner, while the head sweeps three head heights (ADR 0012).
- **Face enrolment.** The camera stays on for about half a minute while the robot asks the owner
  to look straight at it, then turn and tilt their head. The face landmarks it uses to check each
  pose stay in memory (ADR 0011).
- **Helper process.** The camera is opened in a helper process that releases it when its pipe
  closes, even if the robot's own process dies. Frames reach the robot through that pipe, in
  memory (ADR 0010).
- **Respecting the owner's choice.** With detection set to *audio only*, the flow never reaches
  the scan state (scenario test `audio_only_never_uses_camera`). With *camera only*, it never opens
  the microphone to look for bystanders (scenario test `camera_only_never_listens`).
- **Looking closer.** A face that does not clearly match the owner is looked at more closely for
  at most `scan.study_seconds`, with the head following it when `scan.follow.enabled` is on. The
  face boxes and landmarks used to steer the head stay in memory. The event log records only the
  direction, who it turned out to be, whether the face came into full view, the number of head
  moves and frames, and the seconds (`perception.face_studied`). See ADR 0009 and 0012.

### Following never makes speaking more likely

Following a face is meant to get a clearer view of it, never to lose it. A followed face is always
compared: if it never comes into full view, or is lost, the best view so far is compared instead,
so it still counts as a bystander unless it clearly matches the owner (component tests
`test_face_following`).

### The live view shows, never stores

The live view is off by default. When it is on, the runtime keeps in memory (`pasr.live.feed`)
only:

- the latest frame analysed in the current step, dropped together with its face boxes the moment
  the step ends, so the window then shows "Camera off" and never a leftover frame;
- a few seconds of audio levels and the last few labels, dropped when the live view is switched
  off or the robot stops.

A separate window process (`pasr.live.window`) receives the view through a pipe and keeps only
the latest one; the dashboard never shows frames. Nothing is written to disk (the same lint rule
covers it). Only what the robot analyses while listening, scanning, enrolling or calibrating is
shown, never a reminder title, and nothing at all while the owner is away (component tests
`test_live_view_in_flow`).

It does show bystanders' faces on screen, so it is meant for development, or for study sessions
whose participants agreed to it.

### The event log holds no personal content

The event log exists for research, and researchers need numbers, not people's details.
`EventBus.emit` accepts only allow-listed keys with short scalar values, and raises an error for
anything else, so a careless log call cannot leak personal content. Tests check that reminder
titles never appear in the log.

### Uncertainty never leads to speaking aloud

Any error (a missing enrolment, a model mismatch, a crashed plugin, an unreachable device) moves
the flow to `FAILED` and sends the reminder to the watch. An unanswered consent prompt counts as
*no*, and nothing is remembered from it. The price is that a reminder is occasionally sent to the
watch when it could safely have been spoken (ADR 0003).

### Bystander data is minimal

Bystander embeddings are stored only when the owner answers yes or no under the ask-once policy,
because only then is there something worth remembering.

### Sensitive titles are not repeated

After a reminder is set by voice, the robot confirms it out loud but leaves out a sensitive title,
so the confirmation does not disclose what the reminder itself would not.

### Deletion really deletes

SQLite `secure_delete` overwrites deleted rows instead of only marking them free. A reset
checkpoints the write-ahead log, so deleted data does not linger there. Forgetting a bystander
cascades to their embeddings and consent answers.

### Embeddings from different models are never compared

Embeddings from different models are not comparable, and comparing them would give meaningless
scores. So each embedding stores the name of the model that made it. Matching against another
model raises an error, which fails closed, and the dashboard asks the owner to enrol again.

### No network use except one deliberate model download

`pasr models download` (or the first use of a plugin) fetches weights into `models/`; nothing else
opens a connection. Silero and Resemblyzer weights ship inside their packages.

### Only what is needed is inferred

InsightFace is loaded with `allowed_modules=["detection", "recognition"]`, so its age/gender model
is never loaded and the robot cannot guess those attributes.

### Calibration stores nothing about other people

Calibration needs samples of other people to find a good threshold, but it does not need to keep
them. Their samples are scored against the enrolled owner and dropped; the service returns numbers
only (`CalibrationService`), and the event log records only the modality, plugin and threshold.

## Reset

| | Bystanders + embeddings | Consent answers | Preferences (settings) | Owner name, face, voice | Reminders | Event log + pipeline feedback |
|---|---|---|---|---|---|---|
| Reset, keep owner | deleted | deleted | deleted | kept | kept | kept |
| Reset, delete owner | deleted | deleted | deleted | deleted | deleted | kept |
| `--purge-log` | | | | | | deleted |

"Delete last consent" takes back the newest remembered answer. By default it keeps the answer
marked as revoked, for the audit trail; with `--hard` it deletes it outright.

## Models and licences

| Plugin | Weights | Licence |
|---|---|---|
| InsightFace `buffalo_l` (face) | downloaded on first use into `models/insightface/` | **non-commercial research only**: fine for a thesis, but must be revisited for any other use |
| SpeechBrain `spkrec-ecapa-voxceleb` (voice) | downloaded from the Hugging Face hub into `models/speechbrain/` | Apache-2.0 (trained on VoxCeleb; check its terms for other uses) |
| faster-whisper `base` (speech-to-text) | downloaded from the Hugging Face hub into `models/faster-whisper/` | MIT |
| DeBERTa-v3 zero-shot `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (sensitivity; reads only the reminder title, on the laptop) | downloaded from the Hugging Face hub into `models/transformers/` | MIT |
| Resemblyzer (voice, optional) | inside the package | MIT |
| Silero VAD | inside the package | MIT |

`models/` is git-ignored and must not be inside `data/` (a settings validator enforces this).
