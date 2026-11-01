---
title: What you need
description: The robot head, its camera, the laptop's microphone and speaker, a Bangle.js watch, and one command that installs every library they need.
---

| Device | Model in this build | Connects over | Settings group |
|---|---|---|---|
| Robot head | [Ohbot](https://www.ohbot.co.uk), library `ohbot` 4.0.18 | USB serial (`/dev/cu.usbmodem…`) | [`hardware.ohbot`](/reference/settings#hardware.ohbot.port) |
| Voice | macOS `say` through the Ohbot library (lip sync) | the Mac's speaker | `hardware.speaker` |
| Head camera | Logitech HD Webcam C615 | USB | `hardware.camera` |
| Microphone | the laptop's built-in microphone | Core Audio (`sounddevice`) | `hardware.microphone` |
| Watch | Bangle.js 1 with the consent app | Bluetooth LE (Nordic UART) | `hardware.watch` |
| Computer | a Mac, Apple Silicon tested | | |

## Install

```bash
uv sync
```

installs everything the robot needs: `ohbot` and `pyserial` (head and lip-synced speech), `bleak`
(watch), `sounddevice` and `soundfile` (microphone, speaker output, WAV files), `opencv-python`,
`insightface` and `onnxruntime` (camera, face model), `torch`, `torchaudio`, `speechbrain`,
`silero-vad` and `faster-whisper` (voice, voice activity, speech-to-text), and `transformers`
(sensitivity model). The lighter Resemblyzer voice model is optional:
`uv sync --extra resemblyzer` (it builds `webrtcvad` from source).

## Find and test

```bash
uv run pasr hardware list      # serial ports, microphones, speakers, cameras, watches
uv run pasr hardware check     # exercise each device once
```

The dashboard's [Setup](/dashboard/setup) page does the same, and downloads the models with
progress. Scanning and testing need the robot stopped: they take the same lock as a running robot,
so they never fight over the devices.

## Machine-specific settings

Keep settings that belong to this Mac in `.env` (git-ignored) rather than in a profile:

```ini
PASR__HARDWARE__OHBOT__PORT=/dev/cu.usbmodem101
PASR__HARDWARE__SPEAKER__OUTPUT_DEVICE="MacBook Air Speakers"
PASR__HARDWARE__CAMERA__NAME=C615
PASR__HARDWARE__MICROPHONE__DEVICE="MacBook Air Microphone"
```

or save them with `uv run pasr config set hardware.speaker.output_device "MacBook Air Speakers"`
(written to `data/settings.json`). See [Settings](/reference/settings#layers).

## Each device

:::cards 2
bot | [Ohbot head and voice](/hardware/ohbot) | Ports, motors, scan directions, lip sync, where the voice comes out.
watch | [Bangle.js watch](/hardware/watch) | Load the consent app, pair, and what the prompts look like.
camera | [Head camera](/hardware/camera) | Finding it by name, the helper process, reconnects, image folders.
mic | [Microphone](/hardware/microphone) | Choosing a device, chunk size, WAV files.
download | [Models](/hardware/models) | The one-time download, and where the weights live.
wrench | [Troubleshooting](/hardware/troubleshooting) | Permissions, silent lips, a camera that drops off USB.
:::
