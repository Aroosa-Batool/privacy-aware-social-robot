---
title: Watch protocol
description: How the laptop and the Bangle.js talk over Bluetooth LE. One line of JavaScript per request, one line per reply, and a ping that doubles as the owner-presence check.
---

## Transport

Bluetooth LE, Nordic UART Service.

| | UUID |
|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| RX, the PC writes here | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| TX, the PC subscribes to notifications | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

Bangle.js 1 accepts **20-byte** writes, so commands are sent in chunks
(`write(..., response=False)`).

## PC → watch

The watch's Bluetooth console evaluates JavaScript. Each request is one line calling a global of
the consent app. The line starts with `\x10`, which tells Espruino not to echo it (the app also
turns echo off), and ends with a newline. Strings are JSON string literals, ASCII-only (`\uXXXX`
escapes), at most 160 characters of text.

```text
\x10if(typeof consentV2==="function")consentV2("7","Say it out loud?",60);else Bluetooth.println("CONSENT:7:DISPLAY_ERROR")\n
\x10notify("Reminder: Dentist");Bluetooth.println("NOTIFIED:8")\n
\x10Bluetooth.println("PONG:9:"+typeof consent)\n
```

| Request | Watch behaviour | Reply |
|---|---|---|
| Guarded `consentV2(id, text, seconds)` | Buzz and show Yes/No until expiry | `CONSENT:<id>:YES` or `NO` for a button press, `CONSENT:<id>:DISPLAY_ERROR` for an unavailable prompt, silence on expiry |
| `notify(text)` + `println` | Buzz, *Private note* with OK | `NOTIFIED:<id>` (printed by the line itself once `notify` ran) |
| `println("PONG…"+typeof consent)` | none | `PONG:<id>:function` (app loaded) or `PONG:<id>:undefined` |

## Watch → PC

One line per reply, as in the table. Everything else on the console (prompts, errors) is ignored,
and never logged verbatim, because Espruino echoes a failed command, which may contain a reminder
title. An error containing `"consent" is not defined` or `"notify" is not defined` marks the app as
not loaded.

## Presence

The robot checks whether the watch app is reachable before sensing and again immediately before
planned speech. A failed check suppresses speech. A reachable watch may be lying on a table.

## Timeouts

The laptop accepts the first reply for the pending prompt ID and allows five extra seconds for
transport. A timeout, display failure or older app without the corrected prompt leads to private
delivery. Only explicit button choices can create preferences. An unsuccessful private fallback
leaves the reminder marked missed.

## Code

| What | Where |
|---|---|
| Wire format: `consent_command`, `notify_command`, `ping_command`, `chunks`, `LineDecoder`, `parse_reply` | [`src/pasr/hardware/watch/protocol.py`](gh:src/pasr/hardware/watch/protocol.py) |
| Request and response logic: `BangleWatch`; Bluetooth transport: `BleakTransport` | [`src/pasr/hardware/watch/bangle.py`](gh:src/pasr/hardware/watch/bangle.py) |
| The watch app | [`bangle/consent_app.js`](gh:bangle/consent_app.js) |
| Tests against an emulation of the app, and the real app under Node | `tests/component/test_bangle_watch.py`, `tests/unit/test_consent_app_js.py` |

## Notes

- `BleakTransport` finds the watch by name prefix and caches the address in
  `hardware.watch.address`. On macOS that is a CoreBluetooth UUID, valid only on the machine that
  found it; a stale value falls back to a scan.
- The watch drops the connection when idle. The transport's disconnected callback clears the
  client, and `BangleWatch` reconnects before the next request.
- Only one central can hold the link: disconnect the Espruino IDE after loading the app.
