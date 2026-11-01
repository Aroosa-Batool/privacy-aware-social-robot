---
title: Extending PASR
description: Where to add a new algorithm, setting, device, robot app or scenario test, and the rules each one follows.
---

:::cards 2
puzzle | [New algorithm](#new-algorithm) | A plugin behind a protocol, listed on the dashboard automatically.
sliders | [New setting](#new-setting) | One field in the schema, tagged basic or advanced.
plug | [New device](#new-device) | A protocol implementation, wired in the factory.
bot | [New app](#new-app) | A service, an app object, optional CLI commands.
:::

## New algorithm

Write a class with a nested pydantic `Params` model (fields declared with
`pasr.settings.tiers.setting(..., tier=...)`) implementing one protocol from
`perception/protocols.py`, then add a `PluginSpec` to `perception/registry.py`, or call
`registry.register` from your own package. The dashboard lists it and renders its parameters
automatically, and it can be chosen per stage in settings. Walkthrough:
[Swap algorithms](/research/algorithms).

## New setting

Add a field with `setting(default, tier=..., description=...)` to a group in
`settings/schema.py`, then regenerate the reference files:

```bash
uv run pasr config dump --defaults > config/default.yaml      # a test checks it
uv run python website/tools/export_settings.py                # the docs' Settings page
```

The dashboard's settings form is generated from the schema, so the field appears there too.

## New device

Implement the protocol in `hardware/protocols.py` and wire it in `hardware/factory.py`.

- Import the device's library inside `connect()`, `open()` or `stream()`, never at the top of the
  module: the factory imports every adapter.
- Raise `HardwareNotAvailableError` when the library or device is missing.
- Run blocking calls with `asyncio.to_thread`.
- Give the tests a stand-in in `tests/support/devices.py`.

## New app

Follow `apps/reminder/`: a **service** (business logic), an **app** object with `start` and
`stop` that the runtime starts, and optional **CLI** commands. Emit events through the bus with
allow-listed keys only ([event log](/research/event-log#what-the-log-may-hold)).

## New scenario test

Add a YAML file to `tests/scenarios/data/`. The suite runs it on stand-in devices and checks the
expected flow and what was stored. See [Development](/reference/development#scenario-tests).

:::privacy Rules every extension keeps
Never write frames or audio (the lint rule will stop you). Store embeddings only through
`pasr.storage`, tagged with their model. Put only labels and numbers in events. When unsure,
fail closed: raise, and let the flow send the reminder to the watch.
:::
