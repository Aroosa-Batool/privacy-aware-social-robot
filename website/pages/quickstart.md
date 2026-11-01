---
title: Quickstart
description: From a fresh clone to a first reminder. You need a Mac, uv, the Ohbot head with its camera, and a Bangle.js watch with the consent app.
---

PASR runs on the real robot only: there is no simulator in the product (the test suite has
stand-ins, see [Development](/reference/development)). Set aside about an hour the first time,
most of it for the one-time model download and for enrolling your face and voice.

:::note Requirements
macOS (Apple Silicon tested), [uv](https://docs.astral.sh/uv/), Python 3.12 (uv installs it), the
Ohbot head on USB, the head camera, the laptop's microphone and speaker, a Bangle.js watch, and
Chrome or Edge to load the watch app once.
:::

## Install and run

:::steps
@step Clone and install

```bash
git clone https://github.com/Aroosa-Batool/privacy-aware-social-robot.git
cd privacy-aware-social-robot
uv sync          # Python 3.12 and everything the robot needs
```

:::warning Cloned inside iCloud Drive?
iCloud marks files inside `.venv` as hidden, and Python 3.12 then ignores the project's editable
install (`No module named 'pasr'`). Keep the environment outside iCloud, for example add
`export UV_PROJECT_ENVIRONMENT=~/.venvs/privacy-aware-social-robot` to your shell profile.
:::

@step Load the consent app on the watch

Open the [Espruino Web IDE](https://www.espruino.com/ide/), connect to the watch over Bluetooth,
paste `bangle/consent_app.js` into the editor and click **Send to Espruino**. Type `save()` in
the console so it survives a reboot, then **disconnect the IDE**: the watch accepts one
Bluetooth connection, and the robot needs it. Details: [Bangle.js watch](/hardware/watch).

@step Find and test the devices

```bash
uv run pasr hardware list     # serial ports, microphones, speakers, cameras, watches
uv run pasr config set hardware.speaker.output_device "MacBook Air Speakers"
uv run pasr hardware check    # move the head, speak, grab a frame, listen, ping the watch
```

The first run asks for camera, microphone and Bluetooth permission. Allow each prompt; they
belong to your terminal app. The dashboard's [Setup](/dashboard/setup) page does the same.

@step Download the models (the only network access)

```bash
uv run pasr models download
```

Face (InsightFace), voice (SpeechBrain ECAPA), speech-to-text (faster-whisper) and the
sensitivity model go to `models/`, a few hundred MB each. After this the robot works offline.

@step Register yourself as the owner

```bash
uv run pasr setup
```

It asks your name, captures your face (look at the head camera, alone in the frame) and your
voice (speak naturally for about 12 seconds), then asks the two privacy questions: which sensors
may look for bystanders, and what to do with a sensitive reminder when someone is there.

@step Calibrate the thresholds

```bash
uv run pasr calibrate voice --others 1 --apply
uv run pasr calibrate face --others 1 --apply
```

The robot measures how similar you are to yourself and to one other person, and saves a
threshold between the two. See [Calibrate thresholds](/research/calibration).

@step Add a reminder and run the robot

```bash
uv run pasr reminder add "doctor's appointment at 2pm"   # asks: on what date?
uv run pasr run                                          # until Ctrl+C
```
:::

## Or do it all in the dashboard

```bash
uv run pasr dashboard    # opens http://localhost:8501
```

:::steps
@step Settings › Setup

Scan what is connected, test each device, then tick and install the models (once, before
enrolling). [More](/dashboard/setup)

@step Settings › Models

Choose the model for each stage of the experiment. The defaults are the ones the thresholds
were tuned for. [More](/dashboard/models)

@step Start robot, then Profile

**Start robot** is at the top right. On **Profile**, capture your face and voice and make the
privacy choices, including whether to remember your watch answers per person.
[More](/dashboard/profile)

@step Home › Reminders

Type a reminder, add a **Quick test** to watch the whole pipeline in under a minute, or set one
**by voice**. **Home** shows the pipeline live. [More](/dashboard/reminders)
:::

:::tip Try the pipeline in a minute
On **Reminders › Quick test**, keep *Sensitive* on and set *Due in* to 45 seconds. The robot
pings your watch, listens, looks around, and either says the reminder or sends it to your watch.
Follow it on **Home**.
:::

## Next steps

:::cards 2
monitor | [Dashboard tour](/dashboard/tour) | Every page of the dashboard, with recordings.
workflow | [How it works](/how-it-works) | What happens between "reminder added" and "reminder said".
cpu | [Hardware setup](/hardware/overview) | Ports, camera names, speaker routing, permissions.
terminal | [CLI reference](/reference/cli) | Every `pasr` command and flag.
:::
