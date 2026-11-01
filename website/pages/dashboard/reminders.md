---
title: Reminders
description: Type a reminder, add a quick test that runs the whole pipeline in under a minute, or set one by voice, and manage every reminder in one table.
---

Sensitive reminders (for example a doctor's appointment) are said out loud only when the owner is
alone or has agreed on the watch. Everything else is said at its due time, as long as the owner's
watch answers.

::video src=/assets/media/reminders.webm poster=/assets/media/reminders.webp url=localhost:8501/reminders caption="Typing a reminder, choosing its sensitivity, and the Quick test and By voice tabs."

## Type a reminder

Write it the way you would say it: *Dentist appointment on Friday at 3pm*, *Call the bank
tomorrow 9:30*, *Therapist next Monday*. The date and time are read from the text (dateparser);
a missing time becomes `reminder.default_time` (00:00), and a missing date is asked for.

**Sensitivity** has three choices:

| Choice | Effect |
|---|---|
| **Decide automatically** | The sensitivity model reads the title (zero-shot DeBERTa by default). |
| **Sensitive** | Always checked for bystanders before it is said. |
| **Not sensitive** | Said at the due time without checking (the presence check still runs). |

The same from a terminal:

```bash
uv run pasr reminder add "dentist appointment on Friday at 3pm"
uv run pasr reminder add "buy groceries" --date tomorrow --not-sensitive
uv run pasr reminder list            # --all includes delivered and missed ones
uv run pasr reminder delete 42
```

## Quick test

::image src=/assets/media/reminders-quick-test.webp alt="The Quick test tab: a title, a Sensitive switch and Due in (seconds) set to 45, with an Add test reminder button." url=localhost:8501/reminders caption="A quick test is a reminder due in a few seconds."

A reminder due in a few seconds, to watch the whole pipeline on the robot. If it is sensitive,
the robot starts at once. With the microphone and camera it listens for the first 70% of the time
left (at least 15 seconds) and scans the room in the rest; with the microphone only it listens up
to the due time. Quick tests are marked *test* in the table and on Home.

## By voice

::image src=/assets/media/reminders-voice.webp alt="The By voice tab with a Talk to the robot button above the reminders table." url=localhost:8501/reminders

Press **Talk to the robot** (the robot must be running). It asks what to remind you about,
listens, transcribes locally with faster-whisper, and asks for a date if you did not say one.
The audio and the transcript are never stored, and the spoken confirmation leaves out the title
of a sensitive reminder.

## All reminders

The table shows **Upcoming** reminders by default, or **All** of them.

| Column | Meaning |
|---|---|
| `#` | The reminder's id (used by `pasr reminder delete`). |
| due · when | The due time, and how far away it is. |
| title | What the reminder says. |
| sensitive | ✓ Yes / No. |
| decided by | `user` (set by hand) or the model that decided (`zero_shot`, `keyword`). |
| status | `scheduled`, `active` (its flow is running), `spoken`, `sent_to_watch`, `missed` or `cancelled`. |
| origin | `dashboard`, `cli`, `voice` or `test`. |

Select reminders below the table and click **Delete selected** to remove them. A reminder found
more than `reminder.missed_grace_minutes` (10) after its due time, for example after the robot
was off, is marked **missed** instead of being delivered late.
