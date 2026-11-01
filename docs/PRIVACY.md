# Privacy model

The robot exists to protect the owner's private information from people nearby, so it has to
handle everyone's data , the owner's and the bystanders' , carefully itself.

## What is processed, and what is kept

| Data | Where it comes from | Kept? | How long |
|---|---|---|---|
| Camera frames | Head camera, only while enrolling, scanning or calibrating | **Never** , in memory only | Dropped after embedding |
| Audio | Laptop microphone, only while listening, enrolling or calibrating | **Never** , in memory only | Dropped after embedding / transcription |
| Live view (off by default, `live_view.enabled`) | The frames, audio levels and match labels of the listening, scanning, enrolment and calibration steps, shown in a window on the laptop | **Never** , in memory and an OS pipe only | The latest frame only while its step lasts (no last frame stays on screen); a few seconds of levels and the last six labels until the next step, the live view is switched off or the robot stops |
| Researcher-supplied WAV files / image folders | `hardware.microphone.source: wav`, `hardware.camera.source: images` | Read only; the robot never copies or writes them | , |
| Calibration scores | `pasr calibrate` | **Never** (held in memory for the session); only the chosen threshold is saved to `settings.json` | , |
| The robot's own speech (`ohbotspeech.wav`) | Written by the `ohbot` library when it speaks (contains the reminder title) | Deleted after every utterance; lives in `.ohbot/`, never in `data/` | Seconds |
| Speech transcripts | Speech-to-text, when setting a reminder by voice | **Never** | Used only to parse the reminder |
| Owner face / voice embeddings | Enrolment | Yes (`owner_embedding`) | Until re-enrolled, deleted or full reset |
| Bystander embeddings | Detection, **only** with the ask-once policy **and** an answer from the owner | Yes (`bystander_embedding`, ≤ 5 per person) | Until forgotten or reset |
| Consent answers | Owner on the watch | Yes (`consent`), revocable | Until deleted or reset |
| Reminder titles, times, sensitivity | Owner | Yes (`reminder`) | Until deleted or full reset |
| Research event log | Runtime | Yes (`event_log`), **labels and numbers only** | Until purged (`storage.event_log_retention_days`) |

Bystanders are anonymous labels (`B-001`). The robot never knows their names.

## Guarantees and how they are enforced

| Guarantee | Enforcement |
|---|---|
| No raw media on disk | Frames and audio exist only as in-memory `Frame` / `AudioChunk` objects. A lint rule (`ruff` TID251) bans `cv2.imwrite`, `cv2.VideoWriter`, `soundfile.write`, `scipy.io.wavfile.write`, `numpy.save` in `src/`. The test suite checks that, after every scenario test, the only binary data in the database is float32 vectors of the declared size and the data directory holds nothing but the database. `.gitignore` and a pre-commit size limit keep media out of git. |
| Nothing is sensed or said while the owner is away | Every reminder flow first pings the owner's watch over Bluetooth (`CHECKING_PRESENCE`). If it does not answer with the consent app loaded, the flow goes to `OWNER_AWAY` and straight to watch delivery: the microphone and camera are never opened and nothing is said. The watch is pinged again right before speaking. Scenario tests `owner_away_never_senses` and `owner_leaves_before_due` check that neither sensor is opened and nothing is spoken. See ADR 0007. |
| The camera is used only when allowed and needed | Opened only for enrolment and the scan step, closed in `finally`. Face enrolment keeps it on for about half a minute while the robot asks the owner to look straight at it, then turn and tilt their head; the face landmarks it checks each pose with stay in memory (ADR 0011). It is opened in a helper process that releases it when its pipe closes, also if the robot's process dies; frames reach the robot through that pipe, in memory (ADR 0010). With detection set to *audio only* the flow never reaches the scan state (scenario test `audio_only_never_uses_camera`). With *camera only* it never opens the microphone to look for bystanders (scenario test `camera_only_never_listens`). Following faces (`scan.follow.enabled`, off by default) keeps the camera on longer, at most `scan.follow.seconds` per face that is not in full view and matches nobody; the face boxes and landmarks it steers by stay in memory, and the event log records only the direction, whether the face came into full view, the number of head moves and the seconds (`perception.face_followed`). See ADR 0009. |
| Following never makes speaking more likely | A followed face is always compared: if it never comes into full view, or is lost, its best view so far is, so it still counts as a bystander unless it clearly matches the owner (component tests `test_face_following`). |
| The live view shows, never stores | Off by default. The runtime keeps in memory (`pasr.live.feed`) only the latest frame analysed in the current step, dropped with its face boxes the moment the step ends, so the window then shows "Camera off" and never a last frame; and a few seconds of audio levels and the last few labels, dropped when the live view is switched off or the robot stops. A separate window process (`pasr.live.window`) receives the view through a pipe and keeps only the latest one; the dashboard never shows frames. Nothing is written (the same lint rule covers it). Only what the robot analyses while listening, scanning, enrolling or calibrating is kept , never a reminder title, and nothing while the owner is away (component tests `test_live_view_in_flow`). It does show bystanders' faces on screen, so it is meant for development, or for sessions whose participants agreed to it. |
| The event log holds no personal content | `EventBus.emit` accepts only allow-listed keys with short scalar values and raises otherwise. Tests check that reminder titles never appear in the log. |
| Uncertainty never leads to speaking aloud | Any error (missing enrolment, model mismatch, crashed plugin, unreachable device) moves the flow to `FAILED` and sends the reminder to the watch. An unanswered consent prompt counts as *no*, and nothing is remembered. |
| Bystander data is minimal | Embeddings are stored only when the owner gives a yes/no under the ask-once policy, because only then is there something to remember. |
| Sensitive titles are not repeated | After a reminder is set by voice, the robot's confirmation omits a sensitive title. |
| Deletion really deletes | SQLite `secure_delete` overwrites deleted rows. Reset checkpoints the write-ahead log. Forgetting a bystander cascades to their embeddings and consent answers. |
| Embeddings from different models are never compared | Each embedding stores its model name. Matching against another model raises, which fails closed, and the dashboard asks for re-enrolment. |
| No network use except one deliberate model download | `pasr models download` (or the first use of a plugin) fetches weights into `models/`; nothing else opens a connection. Silero and Resemblyzer weights ship inside their packages. |
| Only what is needed is inferred | InsightFace is loaded with `allowed_modules=["detection", "recognition"]`: the age/gender model is never loaded. |
| Calibration stores nothing about other people | Other people's samples are scored against the enrolled owner and dropped; the service returns numbers only (`CalibrationService`), and the event log records only the modality, plugin and threshold. |

## Reset

| | Bystanders + embeddings | Consent answers | Preferences (settings) | Owner name, face, voice | Reminders | Event log |
|---|---|---|---|---|---|---|
| Reset, keep owner | deleted | deleted | deleted | kept | kept | kept |
| Reset, delete owner | deleted | deleted | deleted | deleted | deleted | kept |
| `--purge-log` | | | | | | deleted |

"Delete last consent" revokes the newest remembered answer, keeping it marked as revoked for
the audit trail, or deletes it outright with `--hard`.

## Models and licences

| Plugin | Weights | Licence |
|---|---|---|
| InsightFace `buffalo_l` (face) | downloaded on first use into `models/insightface/` | **non-commercial research only** , fine for a thesis, must be revisited for any other use |
| SpeechBrain `spkrec-ecapa-voxceleb` (voice) | downloaded from the Hugging Face hub into `models/speechbrain/` | Apache-2.0 (trained on VoxCeleb; check its terms for other uses) |
| faster-whisper `base` (speech-to-text) | downloaded from the Hugging Face hub into `models/faster-whisper/` | MIT |
| DeBERTa-v3 zero-shot `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (sensitivity; reads only the reminder title, on the laptop) | downloaded from the Hugging Face hub into `models/transformers/` | MIT |
| Resemblyzer (voice, optional) | inside the package | MIT |
| Silero VAD | inside the package | MIT |

`models/` is git-ignored and must not be inside `data/` (a settings validator enforces it).
