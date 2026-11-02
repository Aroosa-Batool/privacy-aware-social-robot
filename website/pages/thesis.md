---
title: The Master's thesis
nav: The thesis
description: PASR is the software of Aroosa Batool's Master's thesis in Computer Science at the University of Siegen, written in the Ubiquitous Computing group and supervised by Univ.-Prof. Dr. Kristof Van Laerhoven and Atikkhan Nilgar.
---

::thesis-logos

## About the thesis

::thesis-facts

## What it investigates

A robot that reminds its owner of appointments will sometimes have something private to say while
another person is in the room. Asking the owner every time keeps them in control, but being asked
again and again about the same people becomes a burden. The thesis looks at the step from
**consent**, where the robot asks every time, to **privacy management**, where the robot
remembers the owner's answer for each person and applies it by itself, and at how people perceive
a robot that remembers their privacy preferences.

It also compares two ways for the robot to find out who is there: **listening** only, or
listening first and then **looking around** with the camera on its head.

## The study conditions in the software

Each condition of the study is a combination of two settings, chosen on the dashboard's
[Profile](/dashboard/profile) page or in a [profile](/research/profiles) file:

| Condition | What the robot does | Setting |
|---|---|---|
| **Consent** | Asks on the watch whenever someone else is present, and keeps nothing about the person. | `privacy.disclosure_policy: always_ask` |
| **Privacy management** | Asks once per person, then remembers the answer with an anonymous label and embedding. | `privacy.disclosure_policy: ask_once_per_bystander` |
| **Microphone only** | Listens for voices that are not the owner's; the camera stays off. | `privacy.detection_modality: audio_only` |
| **Microphone, then camera** | Listens first, then sweeps the room until the due time for people who stay silent. | `privacy.detection_modality: audio_and_camera` |

What the robot did in each session (who it detected, what it asked, how it delivered each
reminder) is recorded as labels and numbers in the [event log](/research/event-log). See
[Run experiments](/research/overview) for a whole study session.

## Cite this work

```bibtex
@mastersthesis{batool2026consent,
  author = {Aroosa Batool},
  title  = {From Consent to Privacy Management: Investigating Users' Perceptions of a
            Social Robot That Remembers Their Privacy Preferences for Sensitive
            Information Disclosure},
  school = {University of Siegen},
  type   = {Master's thesis},
  year   = {2026},
  note   = {Ubiquitous Computing group, Department of Electrical Engineering and
            Computer Science. Software:
            https://github.com/Aroosa-Batool/privacy-aware-social-robot},
}
```

:::note About the logos
The logos belong to the University of Siegen, its School of Science and Technology (Faculty IV)
and the Ubiquitous Computing group, and show where the thesis was written. The Department of
Electrical Engineering and Computer Science has no logo of its own; its pages carry the faculty's
mark.
:::
