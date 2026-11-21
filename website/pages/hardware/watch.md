---
title: Bangle.js watch
description: The robot's private channel on the owner's wrist. It proves the owner is near, asks for consent with Yes and No, and shows reminders that should not be said aloud.
---

`bangle/consent_app.js` turns a Bangle.js into the robot's private channel:

| Use | What the owner sees |
|---|---|
| **Presence** | Nothing. Every reminder flow pings the watch first; an answer means the owner is near. |
| **Consent** | The watch buzzes: *Robot asks: I noticed someone is with you. Should I say your reminder out loud?* with Yes and No. |
| **Private reminder** | The watch buzzes and shows a *Private note* with an OK button. |

Between prompts it shows *Robot linked, consent ready*. The app keeps the screen awake, so keep
the watch on its charger during a session.

**Buttons.** Bangle.js 1: BTN1 and BTN3 choose, BTN2 confirms. Bangle.js 2: tap. No answer before
the timeout (`consent.timeout_seconds`, 60) counts as **No** for this reminder, and nothing is
remembered.

## Load the app

:::steps
@step Connect the Espruino Web IDE

Open [espruino.com/ide](https://www.espruino.com/ide/) in Chrome or Edge and connect to the watch
over Bluetooth (the icon at the top left).

@step Send the app

Paste `bangle/consent_app.js` into the right-hand editor and click **Send to Espruino**.
Optionally type `save()` in the left console so it survives a reboot.

@step Disconnect the IDE

The watch accepts **one** Bluetooth connection, and the robot needs it.

@step Check from the laptop

```bash
uv run pasr hardware check --device watch
```

or **Setup › Test the devices › Watch**. *"consent is not defined"* means the app is not loaded,
for example after the watch rebooted without `save()`.
:::

To try it by hand in the IDE console: `consent("1","Say it out loud?",20)` and press Yes.

## Pairing and the cached address

The robot finds the watch by name prefix (`hardware.watch.name_prefix`, `Bangle.js`) and caches
its address in `data/settings.json` (`hardware.watch.address`). macOS identifies Bluetooth devices
by a CoreBluetooth UUID rather than a MAC address, so the cached value works only on the Mac that
found it; a stale value simply falls back to a scan.

The watch drops the link when it sleeps. The robot notices and reconnects before each request,
bounded by `reconnect_attempts` × `scan_timeout_seconds` (about 45 s by default). That is also how
long a flow takes to decide the owner is away when the watch is out of range.

:::warning Bluetooth permission
Bluetooth off, or a terminal without Bluetooth permission, is reported as *"Bluetooth is off, or
this terminal has no Bluetooth permission"*. The permission belongs to the app that launches
Python (Terminal, iTerm, VS Code).
:::

The wire format (commands, replies, timeouts) is in [Watch protocol](/reference/watch-protocol).
