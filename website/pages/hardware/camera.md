---
title: Head camera
description: A USB webcam on the head, so turning the head turns the camera. It is opened only while enrolling, scanning or calibrating, in a helper process that can be restarted.
---

## Find it by name

The robot finds the head camera by **name** (`hardware.camera.name`, default `C615`), not by
OpenCV index: indices shift as an iPhone with Continuity Camera comes and goes, and with the head
camera unplugged index 0 is the laptop's own camera. `hardware.camera.index` is used only when the
name is empty.

```bash
uv run pasr hardware list                       # cameras by index and name
uv run pasr config set hardware.camera.name C615
uv run pasr hardware check --device camera      # grab one frame
```

## Open only when needed

OpenCV (AVFoundation on macOS) opens the device in `open()` and releases it in `close()`, so the
camera's LED is dark unless the robot is enrolling, scanning or calibrating. After opening,
`warmup_frames` (5) are discarded while the exposure settles. Frames are 640×480 by default, HxWx3
`uint8` in **BGR** order (OpenCV's convention, which InsightFace expects).

## The helper process

The webcam runs in a helper process, `python -m pasr.hardware.camera.helper`, the only code that
opens a camera through OpenCV ([ADR 0010](/decisions/0010-camera-helper-process)). It sends a frame
per request over a pipe, in memory, and releases the camera when the pipe closes, also when the
robot's process dies.

If no frame arrives for 3 s, the robot starts fresh helpers for up to 10 s. A camera that dropped
off USB and came back costs a few seconds instead of the whole scan, and the dashboard says so in a
toast.

:::warning If the camera drops off USB when the head turns
The toast says the camera *sent no frame … reconnecting it*, or the macOS log shows
`HD Webcam C615 … hardware connection lost`. Give the cable slack and strain relief at the head,
and try a port on the Mac itself instead of a dock.
:::

## An image folder instead of the camera

For repeatable experiments, `hardware.camera.source: images` with `image_dir` replaces the device
with a folder of images (jpg, jpeg, png, bmp), read in name order and cycling. It is read-only:
the robot never writes to it. See [Recorded sources](/research/file-sources).
