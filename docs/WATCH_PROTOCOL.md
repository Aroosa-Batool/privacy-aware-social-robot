# Watch protocol (PC ⇄ Bangle.js 1)

Transport: Bluetooth LE, Nordic UART Service.

| | UUID |
|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| RX , the PC writes here | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| TX , the PC subscribes to notifications | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

Bangle.js 1 accepts **20-byte** writes, so commands are sent in chunks (`write(..., response=False)`).

## PC → watch

The watch's Bluetooth console evaluates JavaScript. Each request is one line calling a global
of the consent app (`bangle/consent_app.js`). The line starts with `\x10`, which tells Espruino
not to echo it (the app also turns echo off), and ends with a newline. Strings are JSON string
literals, ASCII-only (`\uXXXX` escapes), at most 160 characters of text.

```
\x10if(typeof consentV2==="function")consentV2("7","Say it out loud?",60);else Bluetooth.println("CONSENT:7:DISPLAY_ERROR")\n
\x10notify("Reminder: Dentist");Bluetooth.println("NOTIFIED:8")\n
\x10Bluetooth.println("PONG:9:"+typeof consent)\n
```

| Request | Watch behaviour | Reply |
|---|---|---|
| Guarded `consentV2(id, text, seconds)` | Buzz and show Yes/No until expiry | `CONSENT:<id>:YES` or `NO` for the chosen button, `CONSENT:<id>:DISPLAY_ERROR` for an unavailable prompt, silence on expiry |
| `notify(text)` + `println` | Buzz, "Private note" with OK | `NOTIFIED:<id>` (printed by the line itself once `notify` ran; the app's `notify` sends nothing) |
| `println("PONG…"+typeof consent)` | none | `PONG:<id>:function` (app loaded) or `PONG:<id>:undefined` |

## Watch → PC

One line per reply, as in the table. Everything else on the console (prompts, errors) is ignored
by the PC , never logged verbatim, because Espruino echoes a failed command, which may contain a
reminder title. An error containing `"consent" is not defined` or `"notify" is not defined`
marks the app as not loaded.

The ping checks whether the watch app is reachable before sensing and immediately before
planned speech. A failed check suppresses speech. A watch left on a table can still reply.

Each prompt has an outstanding request ID. Expiry or completion retires that ID. The laptop
allows five seconds for transport after the prompt's timeout. A timeout or display error routes
the reminder to the watch. Only an explicit button choice can create a stored preference.
On Bangle.js 1 firmware 2v28, removing a live prompt can leave its button promise pending.
The app listens for the firmware’s screen-removal callback and gives a button press time to
settle. If the screen disappeared without an answer, the app sends `DISPLAY_ERROR` for that
request. A prompt that reaches its own expiry still times out.
The guard detects an older app at request time and takes the display-error path. Old clients
can still call `consent` and will time out on an unfamiliar error reply. A missing private
notification acknowledgement is an error. If fallback also fails, the reminder is marked missed.

## Code

- Wire format: `src/pasr/hardware/watch/protocol.py` (`consent_command`, `notify_command`,
  `ping_command`, `chunks`, `LineDecoder`, `parse_reply`)
- Request/response logic: `src/pasr/hardware/watch/bangle.py` (`BangleWatch`), tested against an
  emulation of the app (`tests/component/test_bangle_watch.py`); the real app runs under Node
  against the same commands (`tests/unit/test_consent_app_js.py`)
- Bluetooth transport: `BleakTransport` in the same file
- Watch app: `bangle/consent_app.js`

## Transport notes

- `BleakTransport` finds the watch by name prefix and caches the address in
  `hardware.watch.address`. On macOS that is a CoreBluetooth UUID, valid only on the machine that
  discovered it; a stale value simply falls back to a scan.
- The watch drops the connection when idle. The transport's disconnected callback clears the
  client, and `BangleWatch` reconnects before the next request.
- Only one central can hold the link: disconnect the Espruino IDE after loading the app.
