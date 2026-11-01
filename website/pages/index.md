---
title: What is PASR?
nav: What PASR is
description: A personal social robot that keeps its owner's private information private, and a research platform for measuring how well it does that.
---

::video src=/assets/media/dashboard-tour.webm poster=/assets/media/home.webp url=localhost:8501 caption="The researcher dashboard: the live pipeline on Home, then Setup, Models, Events, People & consent and Profile."

PASR (privacy-aware social robot) is an [Ohbot](https://www.ohbot.co.uk) robot head with a
camera on it that reminds its owner of appointments. Before it says a **sensitive** reminder out
loud ("your doctor's appointment is at 2 pm"), it checks whether anyone else is in the room,
first by listening and then by looking around, and asks the owner on a **Bangle.js** watch whether
to go ahead. It stores **no audio or video**, only face and voice embeddings.

The same code is a research platform. A dashboard shows the pipeline live and lets a researcher
swap and tune the algorithm of each stage. Recorded WAV files and image folders can stand in for
the microphone and the camera, so an experiment can be repeated on exactly the same input.

::thesis-banner

## What can it do?

:::cards 3
alarm-clock | [Remind you](/dashboard/reminders) | Typed, spoken or quick-test reminders, sorted into sensitive or not by a local model.
ear | [Notice bystanders](/how-it-works#listen) | It hears voices that are not yours, then looks left, front and right for silent people.
watch | [Ask before speaking](/hardware/watch) | A Yes/No prompt on your wrist. No answer counts as no.
users | [Remember consent](/dashboard/people) | Optionally keeps your answer per person, as an anonymous label and an embedding.
activity | [Show its work](/dashboard/home) | A live pipeline, a research log, and an optional window of what it recognises.
flask | [Run experiments](/research/overview) | Swap models per stage, calibrate thresholds, replay recordings.
:::

## Three things to know

**The owner comes first.** Every reminder starts by pinging the owner's watch over Bluetooth. If
the watch does not answer, the owner counts as away: the microphone and the camera stay off,
nothing is said, and the reminder goes to the watch. The watch is asked again right before the
robot speaks. See [owner presence](/how-it-works#presence).

**It fails closed.** Whenever the robot cannot establish that speaking is allowed (an error, a
missing enrolment, a device that stopped answering, an unanswered prompt), it does not speak. The
reminder goes to the watch at its due time. See [ADR 0003](/decisions/0003-fail-closed).

**It keeps numbers, never recordings.** Camera frames and audio exist only in memory. What is
stored is face and voice embeddings (tagged with the model that made them), reminders, consent
answers and a research log of labels and numbers. A lint rule and the test suite enforce it. See
the [privacy model](/reference/privacy).

## What it is made of

| Part | Role |
|---|---|
| **Ohbot** robot head | Turns, nods, blinks and moves its lips while it speaks. Its voice plays on the laptop's speaker. |
| **Logitech C615** webcam on the head | Turning the head turns the camera, so the robot can look around the room. |
| Laptop **microphone** | Listens for voices that are not the owner's. |
| **Bangle.js 1** watch | The owner's private channel: presence check, Yes/No consent, private reminders. |
| A **Mac** running Python 3.12 | Runs everything locally: models, scheduler, database, dashboard. No cloud. |
| **Streamlit dashboard** and the **`pasr` CLI** | Two ways to set it up, run it and watch it. |

## Get started

:::cards 2
rocket | [Quickstart](/quickstart) | From a fresh clone to a first reminder: install, connect, enrol, run.
workflow | [How it works](/how-it-works) | The eight stages every reminder goes through, and who decides what.
:::

## Related topics

- [Take the dashboard tour](/dashboard/tour)
- [Set up the hardware](/hardware/overview)
- [Read the privacy model](/reference/privacy)
- [Browse the design decisions](/decisions/index)
