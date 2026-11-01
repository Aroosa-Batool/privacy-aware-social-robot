---
title: Setup
description: Find and test the robot's devices and install the models, all from one page. Scanning and testing need the robot stopped, because a running robot owns the devices.
---

::image src=/assets/media/setup.webp alt="The Setup page with Stop the robot, What is connected with a Scan button, and Test the devices with Head, Voice, Camera, Microphone and Watch selected." url=localhost:8501/setup caption="While the robot runs, Scan and Run test are disabled and a toast says why."

## What is connected

**Scan** lists the serial ports (the Ohbot), microphones, speakers, cameras (each opened in a
helper process, so the robot never holds a stale device list) and watches nearby over
Bluetooth. It is the same as:

```bash
uv run pasr hardware list
```

Use the names it shows for `hardware.microphone.device`, `hardware.speaker.output_device` and
`hardware.camera.name`. The camera finder looks for the head camera by name (`C615`), because
OpenCV's index changes when an iPhone or another camera comes and goes.

## Test the devices

Pick devices and click **Run test**:

| Device | Test |
|---|---|
| **Head** | Blinks and looks left, front and right. |
| **Voice** | Says "Robot check." on the configured speaker. |
| **Camera** | Takes one frame (kept in memory only). |
| **Microphone** | Listens for a moment and reports the level. |
| **Watch** | Pings the watch, which must have the consent app loaded. A newly found address is saved. |

```bash
uv run pasr hardware check                 # all devices
uv run pasr hardware check --device watch  # one of them
```

## Models

::image src=/assets/media/setup-models.webp alt="The models table on Setup: install checkboxes, stage, model, in use, installed and status for face, speaker, vad, stt and sensitivity." url=localhost:8501/setup

Tick the models to install, once, before enrolling, and click **Install the marked models**.
Afterwards the robot works offline: this is the only time it uses the network (a few hundred MB
each). *bundled* models (Silero VAD) ship inside their Python package. Which model each stage
uses is chosen on [Models](/dashboard/models).

```bash
uv run pasr models status
uv run pasr models download                # the configured models
uv run pasr models download --kind face    # one stage
```
