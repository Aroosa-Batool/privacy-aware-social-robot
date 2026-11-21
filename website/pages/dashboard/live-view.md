---
title: Live view window
nav: Live view
description: Watch face and voice recognition as it happens, in a window on the laptop. Off by default, and nothing in it is ever stored.
---

Whenever the robot listens, scans, enrols or calibrates, the live view opens a window on the
laptop with:

- each analysed **camera frame**, every face boxed and labelled (owner or someone else) with its
  similarity to the owner,
- the **microphone level** and speech probability, with a few seconds of history,
- what each **speech segment** matched, and how closely,
- during calibration, each sample's similarity to the enrolled owner.

Close it with **q** or **Esc**. Closed by hand, it opens again at the next step; it closes with
the robot.

## Switch it on

| Where | How |
|---|---|
| Dashboard | **Live view window** in the top bar, on every page. |
| Terminal, one run | `pasr run --live-view`, `pasr setup --live-view`, `pasr calibrate … --live-view` |
| Always | `uv run pasr config set live_view.enabled true` |

## Colours

Blue for the owner, orange for anyone else, aqua for enrolment samples, grey for unused input. The
set stays distinguishable for every type of colour vision, and every box and row also carries a
text label.

## Why a separate window

A panel inside the dashboard was tried and dropped: re-rendering frames through Streamlit every
half second lagged. The window is a separate process (`python -m pasr.live.window`) fed through a
pipe, because macOS opens windows only on a main thread and the dashboard runs the robot on a
background thread. A slow or stuck window never delays a reminder: the oldest messages are
dropped. ([ADR 0008](/decisions/0008-live-view))

:::privacy It shows, it never stores
The runtime keeps only the latest frame of the current step, dropped the moment the step ends
(the window then shows *Camera off*, never a last frame), plus a few seconds of levels and the
last six labels. It never shows a reminder title and stays shut while the owner is away.

It **does** show bystanders' faces on the laptop's screen, including people who have agreed to
nothing. Use it for development, or for study sessions whose participants agreed to it.
:::
