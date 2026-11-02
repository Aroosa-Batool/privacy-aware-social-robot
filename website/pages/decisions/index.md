---
title: Decision records
nav: Overview
description: Why the robot is built the way it is. Each record states the context, the decision and its consequences, and is kept as written in docs/adr.
---

Architecture decision records (ADRs) capture the choices that shape PASR, from the dashboard
framework to how the camera survives a USB drop. They are rendered here straight from
[`docs/adr`](gh-tree:docs/adr); to propose a change, add a numbered file there.

::adr-list

## The decisions in one line each

| ADR | In one line |
|---|---|
| 0001 | Streamlit for the dashboard, with the robot in-process on a background thread. |
| 0002 | Store embeddings, never audio or images. |
| 0003 | When the robot cannot establish that speaking is allowed, it does not speak. |
| 0004 | Deliver at the due time on both channels, never early. |
| 0005 | Recorded WAV files and image folders stand in for devices; calibration stores one number. |
| 0006 | The product is real-only; stand-ins live in the tests. |
| 0007 | Check the owner's presence on the watch before any sensor is used. |
| 0008 | A live view of recognition, in its own window, off by default. |
| 0009 | Follow a face with the head until it is in full view, off by default. |
| 0010 | The camera in a helper process, and every problem as a toast. |
| 0011 | The robot guides face enrolment through five poses, coaches each one and says how it went. |
| 0012 | Sweep the room row by row until the due time; look closer at a face before deciding who it is. |
| 0013 | Enrol the voice from 30 s of read and free speech; judge another voice on 3 s of its speech. |
| 0014 | The owner marks each reminder's run as worked or not, stored with the models it used. |
