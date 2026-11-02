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
tomorrow 9:30*, *Therapist next Monday*. The date and time are read from the text (dateparser).
A time without a date is today, or tomorrow once that minute has passed (*at 15:00* typed at
15:01 is tomorrow). With neither, the date is asked for; a missing time becomes
`reminder.default_time` (00:00), shown before you save.

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

Switch on **Testing with pictures & recordings** when you show the robot pictures and play
recordings (a video, for example) through speakers instead of having real people in the room.
It is saved when you add the test, before the run starts, and the run logs it, so you can compare
runs by it ([Pipeline feedback](/research/event-log#pipeline-feedback)). It stays as set for
later runs; the same switch is on Home. The camera and microphone work the same either way.

## By voice

::image src=/assets/media/reminders-voice.webp alt="The By voice tab with a Talk to the robot button above the reminders table." url=localhost:8501/reminders

Press **Talk to the robot** (the robot must be running). It asks *What should I remind you
about?*, listens, and transcribes locally with faster-whisper. Then, only if you did not say:

| You said | The robot |
|---|---|
| A date and a time | Saves it. |
| A time only (*at 3pm*) | Takes today, or tomorrow once that minute has passed, and saves it. |
| A date only (*on Friday*) | Asks *At what time should I remind you?* |
| Neither | Asks *When should I remind you?*, then the time if the answer was a date only. |

An answer ends after a one-second pause, so you can pause briefly mid-sentence. If the robot
hears nothing for 15 seconds or cannot make out the answer, it asks again, at most three times
per question: first *Sorry, I didn't catch that.* and the question, then the question with an
example of what to say (*You can say, for example, tomorrow at 3 PM*). After the third miss it
says *Sorry, the reminder is not saved. Please try again, or type it on the dashboard.* The
audio and the transcript are never stored, and the spoken confirmation leaves out the title of a
sensitive reminder. ([ADR 0015](/decisions/0015-asking-for-a-reminder-by-voice))

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
