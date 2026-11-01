# 0007 , Check the owner's presence on the watch first

**Status:** accepted (M3)

**Context.** When a reminder flow started, the robot went straight to listening and scanning. If
the owner was out, it recorded the room (and whoever was in it) for nothing. A reminder would
also be said out loud to an empty room, or to someone who had walked in. The owner wears the
Bangle.js watch, and the watch's Bluetooth link already shows whether the owner is near.

**Decision.** Every reminder flow, sensitive or not, starts with `CHECKING_PRESENCE` and pings
the watch (`Watch.ping`). The owner counts as present only if the watch answers over Bluetooth
with the consent app loaded. Anything else (out of range, no reply, app not loaded, any error)
counts as away. Then the flow goes to `OWNER_AWAY` and delivers to the watch at the due time.
The microphone and camera are never opened, no consent prompt is shown and nothing is said. Just
before speaking, the watch is pinged again; if it does not answer, the reminder goes to the
watch instead. Each check emits an `owner.presence` event with `present: true/false`.

**Consequences.**
- Bluetooth range is not a room: the owner in the next room may still count as present. A
  signal-strength (RSSI) threshold could narrow this; it was not chosen.
- A watch left on the desk counts as the owner being present. Bangle.js 1 cannot reliably tell
  whether it is being worn.
- If the owner is away, the watch is usually out of range too, so the reminder is marked
  missed unless the owner is back by the due time (the robot wakes 7 minutes early for
  sensitive reminders). Non-sensitive reminders, which used to be spoken without the watch,
  now need it.
- When the watch is out of range, the ping retries the connection
  (`hardware.watch.reconnect_attempts` × `scan_timeout_seconds`, about 45 s by default), so a
  flow takes that long to reach `OWNER_AWAY`.
