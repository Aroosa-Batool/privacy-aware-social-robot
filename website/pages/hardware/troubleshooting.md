---
title: Troubleshooting
description: macOS permissions, a silent robot, a camera that drops off USB, a watch that does not answer, and other things that go wrong with real hardware.
---

Every warning and error the robot logs shows as a **toast** on the dashboard, on whatever page is
open, and in the terminal that started it.

## macOS permissions

Camera, microphone and Bluetooth prompts belong to the app that launches Python: Terminal, iTerm
or VS Code. Run `uv run pasr hardware check` from a normal terminal the first time and allow each
prompt. **Over SSH no prompt appears and the devices silently fail.** To fix a denied permission,
open *System Settings › Privacy & Security* and allow your terminal under Camera, Microphone and
Bluetooth.

## Symptoms

### `No module named 'pasr'`

The project lives in iCloud Drive (for example `~/Documents`) and iCloud marked files inside
`.venv` as hidden, so Python ignores the editable install. Move the environment out of iCloud:

```bash
export UV_PROJECT_ENVIRONMENT=~/.venvs/privacy-aware-social-robot   # in your shell profile
uv sync
```

### The lips move but there is no sound

The voice follows the macOS default output. Set the speaker:
`uv run pasr config set hardware.speaker.output_device "MacBook Air Speakers"`.

### The Ohbot is not found

Use the `cu.*` port, not `tty.*`, and set it explicitly if other USB serial devices are attached
(`hardware.ohbot.port`). Unplug and replug the head if `hardware check --device ohbot` hangs.

### The watch does not answer

| Message | Fix |
|---|---|
| *consent is not defined* | The app is not loaded (the watch rebooted without `save()`). Send it again from the Espruino IDE. |
| *Bluetooth is off, or this terminal has no Bluetooth permission* | Switch Bluetooth on; allow the terminal under Privacy & Security › Bluetooth. |
| No answer, then *owner away* | The Espruino IDE still holds the connection, or the watch is out of range. Disconnect the IDE. |

### The camera stops after the head turns

The C615 dropped off USB. The robot reconnects within seconds, but fix the cause: slack and strain
relief at the head, and a port on the Mac rather than a dock.

### The wrong camera opens

Set `hardware.camera.name` to part of the head camera's name (`C615`), so an iPhone with
Continuity Camera or the built-in camera is never picked by index.

### The owner is taken for a stranger (or the other way round)

The threshold does not suit this model, room or person. [Calibrate](/research/calibration) it, and
check that the enrolment was done alone in the frame and in a quiet room.

### A reminder was marked missed

The robot found it more than `reminder.missed_grace_minutes` (10) after its due time, for example
because the robot was off, or the watch was out of range at delivery time.

## Hardware tests

The default test run needs no robot. With the robot connected:

```bash
PASR_HW_TESTS=1 uv run pytest -m hardware      # head, speech, watch ping
```
