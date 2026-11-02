---
title: Settings
description: Every setting, its default and what it does, generated from the settings schema. Basic settings are the ones most people change; Advanced ones tune the details.
---

## Layers

Settings are layered, from lowest to highest priority:

1. built-in defaults (`settings/schema.py`; the reference copy is `config/default.yaml`),
2. an optional `--profile` YAML ([study conditions](/research/profiles)),
3. saved changes, `data/settings.json` (the dashboard, `pasr config set`),
4. `.env` and `PASR__GROUP__FIELD` environment variables (nested with `__`),
5. command-line flags.

```bash
uv run pasr config set identity.voice_threshold 0.4      # saved to data/settings.json
PASR__HARDWARE__OHBOT__PORT=/dev/cu.usbmodem101 uv run pasr run
PASR__SCAN__POSITIONS="[left, right]" uv run pasr run    # lists in YAML syntax
```

Each setting is tagged <span class="pill pill-basic">basic</span> or
<span class="pill pill-advanced">advanced</span>; `pasr config show --level basic|advanced` and the
dashboard show only what you ask for. Link to a setting with its key, for example
[`#identity.voice_threshold`](#identity.voice_threshold).

## Privacy

::settings groups=privacy

## Reminders

::settings groups=reminder

## Consent

::settings groups=consent

## Identity

::settings groups=identity

## Voice activity

::settings groups=vad

## Room scan and face following

::settings groups=scan

## Perception plugins

Each stage takes a `plugin` name and a `params` object with that plugin's own parameters (see
[Swap algorithms](/research/algorithms) and `pasr config show --level advanced`).

::settings groups=perception

## Hardware

::settings groups=hardware

## Storage, logging and live view

::settings groups=storage,logging,live_view

## Study

What the robot is being tested with, for comparing runs; switched on Home and with a quick test.

::settings groups=study

:::note Regenerating this page
The tables come from `website/data/settings.json`. After changing a setting in
`settings/schema.py`, run `uv run python website/tools/export_settings.py` and
`uv run pasr config dump --defaults > config/default.yaml` (a test checks the latter).
:::
