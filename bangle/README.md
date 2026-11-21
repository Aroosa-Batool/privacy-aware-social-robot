# Consent app , Bangle.js

`consent_app.js` is the robot's private channel on the owner's wrist:

- **Consent:** the robot asks "Should I say your reminder out loud?". The watch buzzes and shows
  a Yes/No prompt (Bangle.js 1: BTN1/BTN3 to choose, BTN2 to confirm; Bangle.js 2: tap). No
  answer before the timeout counts as "no" for this reminder, and nothing is remembered.
- **Private reminder:** when the reminder should not be said aloud, it appears on the watch as a
  "Private note" with an OK button.

Between prompts the watch shows "Robot linked , consent ready". The app keeps the screen awake,
so the watch is best kept on its charger during a session.

## Load it (Espruino Web IDE)

1. Open <https://www.espruino.com/ide/> in Chrome or Edge and connect to the watch over
   Bluetooth (top-left icon).
2. Paste `consent_app.js` into the right-hand editor and click **Send to Espruino**.
   Optionally type `save()` in the left console so it survives a reboot.
3. **Disconnect the IDE** , the watch accepts one Bluetooth connection, and the robot needs it.

Check it from the laptop: `uv run pasr hardware check --device watch`, or **Setup → Test** in
the dashboard. "consent is not defined" means the app is not loaded (for example after the watch
rebooted without `save()`).

## How the robot talks to it

The laptop sends one line of JavaScript per request, which the watch's console evaluates, and
reads the lines the app prints back , details in
[docs/WATCH_PROTOCOL.md](../docs/WATCH_PROTOCOL.md).

```js
consent("7", "I noticed someone is with you. Should I say your reminder out loud?", 60)
// → CONSENT:7:YES   or   CONSENT:7:NO   (nothing if unanswered after 60 s)
```

To try it by hand in the IDE console: `consent("1","Say it out loud?",20)` and press Yes.

The app checks only its syntax in CI (`node --check`); the test suite also runs it under Node
against the exact commands the laptop sends (`tests/unit/test_consent_app_js.py`).
