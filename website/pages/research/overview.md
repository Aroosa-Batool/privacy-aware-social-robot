---
title: Run experiments
nav: Overview
description: PASR is also a research platform. Swap the algorithm of each stage, tune and calibrate thresholds, define study conditions as profiles, replay recordings, and export the log.
---

A study with PASR usually varies one thing (the detection modality, the disclosure policy, a
model, a threshold, face following on or off) and measures what the robot did. The pieces:

:::cards 2
gauge | [Calibrate thresholds](/research/calibration) | Measure the owner against other people and pick the threshold between them.
layers | [Study conditions](/research/profiles) | A YAML profile per condition, loaded with one flag or one upload.
folder | [Recorded sources](/research/file-sources) | A WAV file for the microphone, an image folder for the camera: same input, every run.
puzzle | [Swap algorithms](/research/algorithms) | Choose a plugin per stage, or register your own.
list | [Event log and metrics](/research/event-log) | Every state change and score, as labels and numbers, exported as CSV or JSON Lines.
flask | [Scenario tests](/reference/development#scenario-tests) | Scripted rooms on a virtual clock, to check behaviour without the robot.
:::

## A typical session

:::steps
@step Fix the condition

Write the condition as a profile, for example `config/profiles/audio-only-ask-once.yaml`:

```yaml
privacy:
  detection_modality: audio_only
  disclosure_policy: ask_once_per_bystander
reminder:
  wake_lead_minutes: 7
  listen_window_minutes: 5
consent:
  timeout_seconds: 45
```

@step Calibrate for the models in use

`uv run pasr calibrate voice --others 1 --apply` (and `face`, if the camera is used).

@step Run

`uv run pasr run --profile config/profiles/audio-only-ask-once.yaml`, or load the profile on
**Profile › Profiles** and click **Start robot**. Each run is a new **session** in the log.

@step Export

On [Events](/dashboard/events), pick the session and download CSV or JSON Lines.
:::

:::privacy Participants
The robot stores no recordings, but bystanders are analysed live, and with the
[live view](/dashboard/live-view) or [face following](/dashboard/hardware#follow-faces) on they
are shown on screen or followed by the head. Tell participants, and get their agreement, before a
session. The [privacy model](/reference/privacy) lists exactly what is processed and kept.
:::
