---
title: Study conditions (profiles)
nav: Study conditions
description: A profile is a YAML file with the settings one condition changes. Load it with one flag or one upload, and every run under it is comparable.
---

## Write a profile

A profile needs only the settings it changes; everything else keeps its default. The repository
ships one example, `config/profiles/audio-only-ask-once.yaml`:

```yaml
# Example study condition. A profile only needs the settings it changes.
privacy:
  detection_modality: audio_only
  disclosure_policy: ask_once_per_bystander
reminder:
  wake_lead_minutes: 7
  listen_window_minutes: 5
consent:
  timeout_seconds: 45
```

Start from the full reference, `config/default.yaml`, or from the current settings:

```bash
uv run pasr config dump > config/profiles/my-condition.yaml          # effective settings
uv run pasr config dump --defaults > /tmp/defaults.yaml               # built-in defaults
```

## Use it

:::tabs
@tab Terminal

```bash
uv run pasr run --profile config/profiles/audio-only-ask-once.yaml
```

@tab Dashboard

Open **Profile › Profiles: save or load all settings**, upload the YAML file and click
**Apply profile**. *Download* saves the current settings as a profile.
:::

## Conditions worth comparing

| Variable | Setting | Values |
|---|---|---|
| Sensors | `privacy.detection_modality` | `audio_only`, `camera_only`, `audio_and_camera`, `none` |
| Policy | `privacy.disclosure_policy` | `always_disclose`, `always_ask`, `ask_once_per_bystander` |
| Listening time | `reminder.listen_window_minutes`, `listen_until_due` | minutes; listen up to the due time |
| Scanning | `scan.positions`, `scan.follow.enabled` | directions; follow faces or not |
| Models | `perception.*.plugin` | see [Swap algorithms](/research/algorithms) |
| Thresholds | `identity.face_threshold`, `voice_threshold` | from [calibration](/research/calibration) |

## How settings layer

From lowest to highest priority: built-in defaults, the `--profile` YAML, saved changes
(`data/settings.json`), `.env` / `PASR__GROUP__FIELD` environment variables, then command-line
flags. A profile therefore does not override what you saved on the dashboard or in `.env`. Check
what is in effect:

```bash
uv run pasr config diff       # everything that differs from the defaults
uv run pasr config show --level advanced
```
