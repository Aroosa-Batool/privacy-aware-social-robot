# 0012 , Scanning the room until the due time, row by row, and looking closer

**Status:** accepted (amends 0009)

**Context.** The room scan looked left, front and right once, a few frames each, about two
minutes before the due time, then switched the camera off while the robot waited. Someone who
came in during those two minutes, stood (face above the image) or sat low was never seen. And
each frame of a face was judged alone: one poor frame of the owner made a "new bystander", even
when the next frames clearly showed the owner.

**Decisions.**
- The scan **runs until the due time** (on time, the last `wake_lead_minutes −
  listen_window_minutes`, 2 minutes; started late, the last 30% of the time left). A view that
  would not end, with the head back at the front, by the due time is not begun (judged by the
  longest plain view so far), so scanning never makes the reminder late.
- It sweeps **rows** (`scan.tilts`, default level, up, down; the head nods to
  `hardware.ohbot.nod_level` / `nod_up` / `nod_down`) and in each row **every direction**
  (`scan.positions`, default right, front, left), again and again. Each row starts from its
  end nearest to where the head points as the row begins, worked out each time rather than by
  a fixed pattern (`scan_path`): after right, front, left the next row goes left, front, right,
  and after a closer look that left the head elsewhere it starts from there. Between rows the
  head only nods and never swings back across the room. The first
  row is always swept, so a flow that starts after its due time still looks once.
- A face that does not clearly match the owner is **looked at closer** before the sweep goes on:
  the robot stays on it (with `scan.follow.enabled`, the head also turns and nods towards it,
  as in ADR 0009), gathers up to `scan.study_views` (5) views in full view within
  `scan.study_seconds` (10 s; no hurry), and compares their **average** with the owner and the
  remembered bystanders. Several views even out one poor frame; the best view decides if none
  was in full view (fail closed).
- If that face is the owner after all, the sweep goes on. So it does for someone the owner
  **allowed before** (ask-once policy, remembered "yes"): they are noted, recognised only once
  per scan, and the robot keeps looking for anyone else. If it is someone the owner must be
  asked about (new, or remembered without an answer) or **declined** for, the scan **stops**
  there and the flow goes on to the decision: one such person settles it. A scan that saw only
  people allowed before runs to the due time and the reminder is said without asking.
- The same holds while **listening**: the voice of someone allowed before is noted and the robot
  listens on for the whole window, then still scans for silent people (as if it had heard only
  the owner; `reminder.scan_if_only_owner_heard`). It stops listening once it hears someone it
  must ask about or declined for. Two new transitions carry this: `AUDIO_BYSTANDER → SCANNING`
  (heard only allowed people) and `SCANNING → CHECK_MEMORY` (then saw no one).
- If the due time comes without anyone found, the flow reports **found no one**, with the
  number of full sweeps in the reason. One `perception.scan` event per scan (full sweeps,
  frames, seconds, found or not) and one `perception.face_studied` event per closer look
  (direction, identity, in full view, head moves, frames, seconds) replace
  `perception.face_followed`; `scan.follow.seconds` gives way to `scan.study_seconds`.

**Consequences.**
- The camera stays on for the whole scan window (2 minutes on time) instead of a few seconds,
  and the head visibly sweeps. This belongs in the study's information for participants
  (docs/PRIVACY.md).
- Most reminders are delivered at the due time as before; one with a bystander found late is
  delayed by the consent question.
- The nod positions are estimates and must be checked on the real head: if "up" looks down,
  swap `nod_up` and `nod_down`.
