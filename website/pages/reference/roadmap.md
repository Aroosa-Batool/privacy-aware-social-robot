---
title: Roadmap
description: What is built, what comes next, and what is deliberately left out.
---

| Milestone | Scope | Status |
|---|---|---|
| **M0** | Structure, interfaces, state machine, storage, settings, CLI, dashboard, watch app source, tests, CI | <span class="pill pill-ok">Done</span> |
| **M1** | Real Ohbot head and speech; Bluetooth watch transport; the watch app on the device; `pasr hardware list/check` | <span class="pill pill-ok">Done</span> |
| **M2** | Real camera and microphone; InsightFace, Resemblyzer and ECAPA, Silero VAD; real enrolment; threshold calibration; WAV and image-folder sources | <span class="pill pill-ok">Done</span> |
| **M3** | Local speech-to-text (faster-whisper) for voice reminders; simulation removed from the product | <span class="pill pill-ok">Done</span> |
| **M4** | Experiment tooling and metrics export; researcher handbook; optional Google Calendar import | <span class="pill pill-advanced">Next</span> |

## Deliberately not built (yet)

- Cloud deployment or battery operation
- Multiple owners or logins
- A mobile app
- Any cloud or LLM service: everything runs locally
- Model training
- Raw media storage, or live video in the dashboard

## Known limitations

- **Bluetooth range is not a room.** The owner in the next room may count as present, and a watch
  left on the desk counts as the owner ([ADR 0007](/decisions/0007-owner-presence-first)).
- **The gap before the due time.** Someone who arrives between the check and the due time is not
  detected; `reminder.listen_until_due` narrows the gap ([ADR 0004](/decisions/0004-deliver-at-due-time)).
- **The camera cable.** A reconnect cannot help a camera that stays off USB
  ([ADR 0010](/decisions/0010-camera-helper-process)).
