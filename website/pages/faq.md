---
title: FAQ
description: Short answers to the questions people ask first, about privacy, hardware and running the robot.
---

## Privacy

### Does the robot record me?

No. Camera frames and audio exist only in memory, long enough to compute an embedding or a
transcript, and are then dropped. A lint rule bans the functions that would write them to disk
(`cv2.imwrite`, `soundfile.write`, …) and the tests check that the data folder holds nothing but
the database. See the [privacy model](/reference/privacy).

### What does it store about other people?

Nothing, unless the owner chose to remember watch answers (*ask once per person*) **and**
answered Yes or No about that person. Then it keeps an anonymous label such as `B-001`, up to
five embeddings and the answer. It never knows anyone's name. Forget a person on
[People & consent](/dashboard/people).

### Does anything go to the cloud?

No. Every model runs on the laptop. The only network access is the one-time model download
(`pasr models download`, or the Setup page).

### What happens if the robot is unsure?

It does not speak. Errors, missing enrolment, an unreachable device and an unanswered prompt all
send the reminder to the watch instead ([fail closed](/decisions/0003-fail-closed)).

### Can people see themselves on the screen?

Only if the [live view](/dashboard/live-view) is switched on, which it is not by default. It shows
what the robot analyses while it listens or scans, including bystanders' faces, and stores nothing.
Use it for development or for study sessions whose participants agreed to it.

## Using it

### Why did my reminder go to the watch instead of being said?

Look at the reminder's steps on [Home](/dashboard/home) or in [Events](/dashboard/events). The
usual reasons, in order: the watch did not answer the presence check (*owner away*), someone else
was heard or seen and you answered No or did not answer, or an error occurred (`flow.error`).

### Why does it say a non-sensitive reminder needs the watch?

Every reminder starts with the presence check, sensitive or not. If the watch is out of range,
the owner counts as away and the robot says nothing ([ADR 0007](/decisions/0007-owner-presence-first)).

### How long before a reminder does the robot start?

7 minutes for a sensitive reminder with the microphone, 2 minutes with the camera only, and at
the due time for anything else. A reminder added later than that starts at once.

### Can I set a reminder by voice?

Yes, on **Reminders › By voice** (the robot must be running). Press the button, say what to
remind you about; the robot asks for a date if you did not give one. Neither the audio nor the
transcript is kept, and the robot's confirmation leaves out a sensitive title.

## Hardware

### Which watch does it need?

A Bangle.js 1 with `bangle/consent_app.js` loaded. A Bangle.js 2 runs the app too (tap instead of
buttons). See [Bangle.js watch](/hardware/watch).

### The head moves its lips but I hear nothing.

The Ohbot has no speaker; its voice plays on the Mac. Set `hardware.speaker.output_device` (for
example `MacBook Air Speakers`) so it does not follow the macOS default to AirPods or a display.

### The camera stops after the head turns.

The USB cable is probably pulling. The robot reconnects a stalled camera within seconds
([ADR 0010](/decisions/0010-camera-helper-process)), but give the cable slack at the head and try
a port on the Mac itself. More in [Troubleshooting](/hardware/troubleshooting).

## Research

### Can I repeat an experiment on the same input?

Yes. A WAV file can stand in for the microphone and an image folder for the camera. See
[Recorded sources](/research/file-sources).

### Can I plug in my own model?

Yes: implement the protocol for the stage and register a `PluginSpec`. The dashboard lists it and
renders its parameters automatically. See [Swap algorithms](/research/algorithms).
