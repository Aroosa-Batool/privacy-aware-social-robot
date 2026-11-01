---
title: Dashboard tour
description: The researcher dashboard runs the robot, shows the pipeline live and holds every setting. Start it with uv run pasr dashboard and open localhost:8501.
---

```bash
uv run pasr dashboard            # http://localhost:8501
uv run pasr dashboard --port 8600
```

The dashboard is a Streamlit app that keeps **one robot runtime** alive on a background thread
([ADR 0001](/decisions/0001-streamlit-dashboard)). Pages that only read or write data (reminders,
consent, settings) work while the robot is stopped; listening, scanning and enrolment need it
running.

::video src=/assets/media/dashboard-tour.webm poster=/assets/media/home.webp url=localhost:8501 caption="A walk through the dashboard while a sensitive test reminder is listening for other voices."

## The top bar

Every page shares the same bar:

| Element | What it does |
|---|---|
| **PASR** logo | The robot icon; the browser tab shows it too. |
| **Home ▾ · Settings ▾ · Info ▾ · Profile** | The menu. Hover a section (or tap it on a touch screen) to see its pages; click it to open the first one. |
| **Live view window** | Switches the [live view](/dashboard/live-view) on or off. Off by default. |
| **Running** / **Stopped** | Whether the robot runtime is up. |
| **Start robot** / **Stop** | Starts or stops the runtime. It owns the head, camera, microphone and watch while it runs. |
| **⋮** | Streamlit's menu: rerun the page, switch between light and dark. |

Problems never appear as boxes on a page: every warning and error the robot logs shows once as a
**toast** at the bottom right, on whatever page is open (green for done, yellow for a warning,
red for an error).

## The pages

:::cards 2
home | [Home](/dashboard/home) | Policy, detection, the next reminder and the live pipeline.
alarm-clock | [Reminders](/dashboard/reminders) | Type one, add a quick test, or set one by voice.
user | [Profile](/dashboard/profile) | The owner's name, face, voice and privacy choices.
users | [People & consent](/dashboard/people) | Remembered bystanders and the consent history.
list | [Events](/dashboard/events) | The research log, filterable and downloadable.
plug | [Setup](/dashboard/setup) | Find and test devices, install models.
sliders | [Models](/dashboard/models) | The algorithm and parameters of each stage.
scan-face | [Hardware](/dashboard/hardware) | Room scan directions and face following.
rotate-ccw | [Reset](/dashboard/reset) | Delete bystanders, consent and preferences, optionally the owner.
app-window | [Live view](/dashboard/live-view) | A window of what the robot recognises, as it happens.
:::

## Running and stopped

| | Robot stopped | Robot running |
|---|---|---|
| Add, edit, delete reminders | ✓ | ✓ (the scheduler picks changes up within 10 s) |
| Change settings and privacy choices | ✓ | ✓ |
| Scan and test devices, install models (Setup) | ✓ | stop it first: the robot owns the devices |
| Enrol face and voice (Profile) | | ✓ |
| Set a reminder by voice | | ✓ |
| Deliver reminders | | ✓ |

:::info One robot per data folder
`data/.runtime.lock` allows one runtime per data directory, so a reminder is never delivered
twice. If `pasr run` is already running in a terminal, the dashboard cannot start a second robot.
:::
