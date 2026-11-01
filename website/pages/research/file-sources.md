---
title: Recorded sources
description: A WAV file can stand in for the microphone and a folder of images for the camera, so an experiment can be repeated on exactly the same input. The robot only reads them.
---

The robot never stores media ([ADR 0002](/decisions/0002-embeddings-only)), so experiments cannot
be replayed from anything it kept. Instead, a researcher supplies recordings, and they behave
exactly like the devices they replace. They carry no hidden information about who is in them.
([ADR 0005](/decisions/0005-file-sources-and-calibration))

## Audio from a WAV file

```bash
ffmpeg -i session.m4a -ar 16000 -ac 1 session.wav     # the configured sample rate, once
uv run pasr config set hardware.microphone.source wav
uv run pasr config set hardware.microphone.wav_path ~/experiments/session.wav
```

- The file must be at `hardware.microphone.sample_rate` (16 kHz). There is no resampling
  dependency, so results are bit-exact and reproducible.
- The stream **ends with the file** instead of looping: looping would double-count speakers in
  calibration and hide a too-short recording.
- `wav_realtime: true` (default) paces chunks on the robot's clock, so `pasr run` behaves like a
  room; `false` delivers them as fast as possible.

## Faces from an image folder

```bash
uv run pasr config set hardware.camera.source images
uv run pasr config set hardware.camera.image_dir ~/experiments/frames
```

Images (jpg, jpeg, png, bmp) are read in name order and cycle. Name them so the order matches the
scan: for example `01-left.jpg`, `02-front.jpg`, `03-right.jpg`.

## Or in `.env`

```ini
PASR__HARDWARE__MICROPHONE__SOURCE=wav
PASR__HARDWARE__MICROPHONE__WAV_PATH=~/experiments/session.wav
PASR__HARDWARE__CAMERA__SOURCE=images
PASR__HARDWARE__CAMERA__IMAGE_DIR=~/experiments/frames
```

Switch back with `source: device`.

:::warning Keep recordings out of the repository
`.gitignore` excludes audio, video and image files, and a pre-commit hook rejects files over
500 KB. Keep recordings in a folder of their own, outside the project, and handle them under your
study's data agreement.
:::
