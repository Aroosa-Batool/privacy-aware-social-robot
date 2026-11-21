---
title: Microphone
description: The laptop's microphone through sounddevice, as mono 16 kHz audio in 32 ms chunks. Choose it by name, or replace it with a WAV file.
---

## Choose the device

`hardware.microphone.device` is a name from `pasr hardware list`; empty means the system default.
Choose one explicitly if AirPods or a display's microphone keep taking over:

```bash
uv run pasr config set hardware.microphone.device "MacBook Air Microphone"
uv run pasr hardware check --device microphone    # listens briefly, prints the level (RMS)
```

## The audio format

| Property | Value | Why |
|---|---|---|
| Channels | mono | Speaker embeddings and VAD expect one channel. |
| Sample rate | `sample_rate`, 16 kHz | What the voice models are trained on. |
| Chunk | `chunk_ms`, 32 ms = 512 samples | The window Silero VAD needs. |
| Type | float32 | |

The PortAudio callback hands chunks to the robot's event loop. Overflows are counted and logged,
never written anywhere. The robot listens only during the listening step, enrolment, calibration
and a voice reminder.

## A WAV file instead of the microphone

`hardware.microphone.source: wav` with `wav_path` replaces the device with a researcher-supplied
WAV file (mono or stereo) at **exactly** `sample_rate`. Resample first:

```bash
ffmpeg -i in.wav -ar 16000 -ac 1 out.wav
```

The stream ends with the file (it does not loop, which would double-count speakers).
`wav_realtime: true` paces chunks like a room; `false`, or `pasr calibrate --fast`, delivers them
as fast as possible. See [Recorded sources](/research/file-sources).
