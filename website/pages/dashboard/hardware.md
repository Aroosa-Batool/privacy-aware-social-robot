---
title: Hardware
description: How the robot's head moves while it looks for silent bystanders, and whether it follows a face it does not see in full.
---

::video src=/assets/media/hardware.webm poster=/assets/media/hardware-poster.webp url=localhost:8501/hardware caption="Room scan positions and timing, then the switch for following faces."

## Room scan

Before a sensitive reminder, if no other voice was heard (or only the owner's), the head looks
in these directions for silent bystanders.

| Field | Setting | Default |
|---|---|---|
| **Positions** | `scan.positions` | left, front, right |
| **Settle seconds** | `scan.settle_seconds` | 0.6: wait after a move before looking |
| **Frames per position** | `scan.frames_per_position` | 3 frames analysed per direction |
| **Head speed** | `scan.head_speed` | 5 (Ohbot motor speed, 1 to 10) |

Where *left*, *front* and *right* point is set per head with `hardware.ohbot.turn_left`,
`turn_front` and `turn_right` (2, 5 and 8 on the Ohbot's 0 to 10 scale). Calibrate them with
`pasr hardware check --device ohbot` while watching where the camera points.

## Follow faces

::image src=/assets/media/hardware-follow.webp alt="The Follow faces section with its switch on, and Save and Discard buttons." url=localhost:8501/hardware

A face that is cut off, too small, unclear or turned away gives a poor match: the owner can look
like a stranger, and a remembered bystander like a new one. With **Follow faces that are not in
full view** on, the head turns and nods towards such a face until it is in full view, then
compares it with the owner and the remembered bystanders. The camera stays on while the head
follows, at most `scan.follow.seconds` (5 s) per face.

It is **off by default**, so experiments can compare it with fixed directions. Its gains and signs
depend on the head; see [Ohbot head](/hardware/ohbot#tune-face-following) and
[ADR 0009](/decisions/0009-follow-faces).

:::note Following never makes speaking more likely
A followed face is always compared in the end, with the best view the robot got. If it never
comes into full view or is lost, it still counts as a bystander unless it clearly matches the
owner.
:::
