---
title: CLI
description: Every pasr command. Run them with uv run pasr …; add --help to any command for its options.
---

```bash
uv run pasr --help
uv run pasr reminder add --help
```

## Overview

| Command | What it does |
|---|---|
| [`pasr run`](#pasr-run) | Run the robot until Ctrl+C |
| [`pasr dashboard`](#pasr-dashboard) | Open the researcher dashboard |
| [`pasr setup`](#pasr-setup) | Owner, face and voice enrolment, the two privacy questions |
| [`pasr calibrate`](#pasr-calibrate) | Measure owner-vs-others similarity, suggest and save a threshold |
| [`pasr hardware`](#pasr-hardware) | `list` and `check` the devices |
| [`pasr models`](#pasr-models) | `status` and `download` of model weights |
| [`pasr reminder`](#pasr-reminder) | `add`, `list` and `delete` reminders |
| [`pasr consent`](#pasr-consent) | `list` and `delete-last` remembered consent |
| [`pasr reset`](#pasr-reset) | Reset the app |
| [`pasr config`](#pasr-config) | `show`, `set`, `diff`, `dump`, `reset` settings |

## pasr run

Run the robot (scheduler and reminder flows) until Ctrl+C. It prints each state change and every
consent request and delivery.

| Option | |
|---|---|
| `--profile FILE` | A YAML settings profile, layered under saved changes and `.env`. |
| `--live-view` | Open the [live view](/dashboard/live-view) window for this run. |
| `-v`, `--verbose` | Debug logging. |

```text
18:47:20  reminder #85: IDLE → WAKING  (time to prepare the reminder)
18:47:21  reminder #85: WAKING → CHECKING_PRESENCE  (asking the owner's watch before using any sensor)
18:47:21  reminder #85: CHECKING_PRESENCE → LISTENING  (sensitive reminder: listening for other voices)
```

## pasr dashboard

Open the researcher dashboard (Streamlit) at `http://localhost:8501`.

| Option | |
|---|---|
| `--port N` | Port for the web dashboard (8501). |

## pasr setup

Register the owner: name, face, voice, and the two privacy questions. Interactive by default.

| Option | |
|---|---|
| `--name TEXT` | Owner's name. |
| `--modality` | `none`, `audio_only`, `camera_only` or `audio_and_camera`. |
| `--policy` | `always_disclose`, `always_ask` or `ask_once_per_bystander`. |
| `--enroll / --no-enroll` | Enrol face and voice (on). |
| `--face / --no-face`, `--voice / --no-voice` | Skip one of them. |
| `--live-view` | Watch the samples come in. |

## pasr calibrate

```bash
pasr calibrate face|voice [--others N] [--samples N] [--apply] [--wav F …] [--images DIR …] [--fast] [--live-view]
```

Measure owner-vs-others similarity with the current plugins and suggest a threshold. Nothing but
the chosen threshold is stored. See [Calibrate thresholds](/research/calibration).

| Option | |
|---|---|
| `face` or `voice` | Which threshold. |
| `--others N` | Other people to capture live (1; 0 = owner only). |
| `--samples N` | Samples per person (the enrolment count). |
| `--apply` | Save the suggestion without asking. |
| `--wav FILE` | Voice from WAV files: first the owner, then others (repeatable). |
| `--images DIR` | Faces from image folders: first the owner, then others (repeatable). |
| `--fast` | Do not pace WAV files in real time. |
| `--live-view` | Show each sample's similarity in the live view. |

## pasr hardware

```bash
uv run pasr hardware list                       # serial ports, microphones, speakers, cameras, watches
uv run pasr hardware list --scan-seconds 10     # scan longer for the watch (5 s)
uv run pasr hardware check                      # every device
uv run pasr hardware check -d ohbot -d watch    # some of them
```

Devices for `check`: `ohbot`, `speaker`, `camera`, `microphone`, `watch`. Both need the robot
stopped. See [Setup](/dashboard/setup).

## pasr models

```bash
uv run pasr models status                  # installed? weights downloaded?
uv run pasr models download                # the configured models
uv run pasr models download -k face -k vad # some stages
```

Downloading is the only time the robot uses the network. See [Models](/hardware/models).

## pasr reminder

```bash
uv run pasr reminder add "doctor appointment at 2pm tomorrow"
uv run pasr reminder add "therapist" --date "next monday" --sensitive
uv run pasr reminder list            # upcoming
uv run pasr reminder list --all      # include delivered and missed
uv run pasr reminder delete 42
```

| Option of `add` | |
|---|---|
| `--date TEXT` | The answer to the date question, e.g. `tomorrow`. |
| `--sensitive / --not-sensitive` | Override the sensitivity classifier. |

## pasr consent

```bash
uv run pasr consent list
uv run pasr consent delete-last           # revoke the newest answer (kept, marked revoked)
uv run pasr consent delete-last --hard    # delete the record instead
```

## pasr reset

```bash
uv run pasr reset                         # asks: keep or delete the owner?
uv run pasr reset --keep-owner --yes
uv run pasr reset --delete-owner --purge-log --yes
```

| Option | |
|---|---|
| `--delete-owner / --keep-owner` | Also delete the owner's face and voice data, name and reminders. |
| `--purge-log` | Also delete the research event log. |
| `-y`, `--yes` | Do not ask for confirmation. |

Stop the robot (or the dashboard's runtime) first.

See [Reset](/dashboard/reset) for exactly what is deleted.

## pasr config

```bash
uv run pasr config show                       # basic settings
uv run pasr config show --level advanced      # all of them
uv run pasr config set privacy.disclosure_policy ask_once_per_bystander
uv run pasr config set scan.positions "[left, right]"   # values in YAML syntax
uv run pasr config diff                       # what differs from the defaults
uv run pasr config dump > my-profile.yaml     # effective settings as YAML
uv run pasr config dump --defaults            # built-in defaults
uv run pasr config reset                      # restore defaults (keeps owner, reminders, bystanders)
```

`set` writes to `data/settings.json`. Every key is listed in [Settings](/reference/settings).
