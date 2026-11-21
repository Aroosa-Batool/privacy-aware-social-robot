---
title: Ohbot head and voice
nav: Ohbot head & voice
description: Connecting the Ohbot over USB, how the robot drives its motors safely from one thread, where the scan looks, and how to route its voice to the right speaker.
---

## Connect

The Ohbot appears as a USB serial port, on this Mac `/dev/cu.usbmodem101` (use `cu.*`, not
`tty.*`). With `hardware.ohbot.port: auto` the library probes every `*usb*` serial port; set the
port explicitly if other USB serial devices are attached:

```bash
uv run pasr config set hardware.ohbot.port /dev/cu.usbmodem101
uv run pasr hardware check --device ohbot   # blinks, looks left, front, right
```

## How the robot drives it

- **The import has side effects.** `import ohbot` creates `ohbotData/` in the current directory,
  copies motor definitions there and connects to the robot. The adapter imports it only inside
  `OhbotDriver.ensure_started`, after switching the process to `<project>/.ohbot/`
  (git-ignored). Nothing of this lands in `data/`.
- **The library is not thread-safe.** `say()` starts a lip-sync thread that calls `move()`.
  `OhbotDriver` is the single owner: one lock around every call, shared by the head and the
  speaker, so lip-sync moves never interleave with scan moves.
- `look()` returns after a time estimate (`hardware.ohbot.move_seconds`, scaled by distance and
  speed); the scan then waits `scan.settle_seconds` before grabbing frames.

## Motors and scan directions

| Motor | Number | Range |
|---|---|---|
| HEADNOD | 0 | 0 to 10 |
| HEADTURN | 1 | 0 to 10 |
| EYETURN | 2 | 0 to 10 |
| LIDBLINK | 3 | 0 to 10 |
| TOPLIP | 4 | 0 to 10 |
| BOTTOMLIP | 5 | 0 to 10 |
| EYETILT | 6 | 0 to 10 |

*Left*, *front* and *right* for the room scan are HEADTURN positions
`hardware.ohbot.turn_left`, `turn_front` and `turn_right` (2, 5, 8). Calibrate them on the real
head with `pasr hardware check --device ohbot` and watch where the camera points.

## Tune face following

[Following faces](/dashboard/hardware#follow-faces) uses `nudge()`: HEADTURN and HEADNOD move by
small steps within 0 to 10. To tune it, switch on the [live view](/dashboard/live-view), stand at
the edge of the camera's view and run a sensitive [quick test](/dashboard/reminders#quick-test).

| If the head… | Change |
|---|---|
| turns away from you | switch on `scan.follow.invert_turn` |
| nods away from you | switch on `scan.follow.invert_nod` |
| overshoots | lower `turn_gain` / `nod_gain` |
| needs many small steps | raise `turn_gain` / `nod_gain` |

The gain is the number of motor units for a face at the edge of the image, so about half the
camera's field of view in motor units.

## Speech and where the voice comes out

The Ohbot has **no speaker of its own**. `ohbot.say(text, lipSync=True)` runs macOS `say -o` into
`.ohbot/ohbotData/ohbotspeech.wav`, plays it and moves the lips. The driver deletes that file after
every utterance (it contains the reminder title) and strips shell metacharacters from the text,
because the library builds a shell command.

Set the output device, or the voice follows the macOS default (AirPods, a display) while the
robot moves its lips silently:

```bash
uv run pasr hardware list                  # speaker names
uv run pasr config set hardware.speaker.output_device "MacBook Air Speakers"
```

| `hardware.speaker.backend` | Behaviour |
|---|---|
| `ohbot` (default) | The library generates the speech and drives the lips; `sounddevice` plays the file on `output_device`. |
| `macos_say` | `say` directly (argv, no file, no lip sync), on `output_device` via `say -a`. `hardware.speaker.voice` picks the voice. |
