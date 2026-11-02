---
title: Home and the live pipeline
nav: Home
description: What the robot is set to do, when it starts next, and where the current reminder is in its eight stages, refreshed every second.
---

::image src=/assets/media/home.webp alt="The Home page: policy, detection and next reminder cards above the pipeline, which shows Schedule, Wake and Presence done and Listen running." url=localhost:8501 caption="A sensitive test reminder: the watch answered (Presence), and the robot is listening for other voices."

## The three cards

| Card | Shows |
|---|---|
| **Policy** | The disclosure policy: *always disclose*, *always ask* or *ask once per bystander*. |
| **Detection** | Which sensors may look for bystanders: *audio and camera*, *audio only*, *camera only* or *none*. |
| **Next reminder** | When the robot starts preparing the next reminder (counted down), or that it is on it now. *(test)* marks a quick test. |

When the robot is stopped, Home lists the next five reminders instead, and a yellow toast lists
anything left to set up (no owner, no face or voice enrolled, models missing).

## The pipeline

The row of eight stages follows the reminder being handled right now, or the last one:

| Stage | Done when |
|---|---|
| **Schedule** | The reminder exists and its wake-up time has come. |
| **Wake** | The flow started (`WAKING`). |
| **Presence** | The owner's watch answered the ping. Not reached if the owner is away. |
| **Listen** | Listening ended: a stranger heard, or not. Skipped with the camera only. |
| **Scan** | The head swept the room until the due time, or until it recognised someone. Skipped with audio only or when a stranger was already heard. |
| **Decide** | The policy chose speak, ask or watch. |
| **Consent** | The owner answered on the watch, or the prompt timed out. Skipped when not needed. |
| **Deliver** | Said out loud or shown on the watch, at the due time. |

The current stage is blue and labelled **NOW**; finished stages are green with a tick; stages the
flow skipped or never reached stay grey. A failed stage turns red, and the reason appears as a
toast.

**Steps of this reminder** lists each state change with its time and a short reason, for example
`CHECKING_PRESENCE` *asking the owner's watch before using any sensor*. **Recent events** below it
shows the latest research-log entries: perception scores, presence checks, deliveries.

:::tip Watch the whole pipeline in under a minute
Add a [Quick test](/dashboard/reminders#quick-test) and come back to Home. Stages light up one by
one, and the live view (if on) opens when the robot starts listening.
:::

## Related topics

- [How it works](/how-it-works), stage by stage
- [The state machine](/reference/state-machine) behind the pipeline
- [Events](/dashboard/events), the full research log
