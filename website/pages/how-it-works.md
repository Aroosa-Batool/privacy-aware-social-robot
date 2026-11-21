---
title: How it works
description: The eight stages every reminder goes through, from the moment it is added to the moment it is said out loud or shown privately on the watch.
---

The dashboard's **Home** page shows each reminder as a row of eight stages. They are the same
stages the robot's state machine walks through ([full diagram](/reference/state-machine)).

::pipeline

## Profile: the owner registers

Before anything else the owner registers once, on the dashboard's [Profile](/dashboard/profile)
page or with `pasr setup`. The robot captures **embeddings** of the owner's face (4 images in each
of 5 poses) and voice (30 seconds of speech, read aloud from a text on the screen and then in
their own words, stored as samples of about 4 seconds) and asks two questions:

| Question | Choices | Setting |
|---|---|---|
| How may the robot check whether someone else is in the room? | microphone only · camera only · microphone and camera · neither | `privacy.detection_modality` |
| What should it do with a sensitive reminder when someone else may hear it? | always say it · ask on the watch every time · ask once per person and remember | `privacy.disclosure_policy` |

## Schedule

A reminder is typed on the dashboard, added with `pasr reminder add`, or spoken (the robot
transcribes it locally with faster-whisper and never keeps the audio or the text of what you
said). A time without a date is today, or tomorrow once that minute has passed. Said to the
robot, a reminder without a time gets asked *When should I remind you?* or *At what time should
I remind you?*, each at most three times ([ADR 0015](/decisions/0015-asking-for-a-reminder-by-voice));
typed, it asks for a missing date and uses `reminder.default_time` (midnight) for a missing time.

A **sensitivity** model then reads the title: *doctor's appointment* is sensitive,
*buy groceries* is not. The default is a zero-shot DeBERTa model that checks the title against a
list of topics (health, therapy, money, the police, a job interview, a password, …); a keyword
list is the lightweight alternative. You can always override the decision by hand.

## Wake

The scheduler checks the database every 10 seconds. A reminder's flow starts at its wake-up
time:

- **Sensitive and checked** (not *always say it*, detection not *neither*): `wake_lead_minutes`
  before it is due (7 minutes by default), so the robot has time to listen and look around.
- **Camera only**: only 2 minutes early. It does not listen, so it wakes later and scans.
- **Not sensitive**: at the due time.

A reminder added only a few minutes before it is due (a **Quick test**, for example) starts at
once. With the microphone and camera, the robot then listens for the first 70% of the time left
(at least `min_listen_seconds`, 15 s) and scans in the rest, so the scan finishes before the due
time.

## Presence

Before the microphone or camera is used, the robot **pings the owner's watch** over Bluetooth.
The owner counts as present only if the watch answers with the consent app loaded. No answer,
out of range, app not loaded, any error: the owner is **away**. Then nothing is sensed, nothing is
said, and the reminder goes to the watch at its due time. The ping is repeated right before the
robot speaks. ([ADR 0007](/decisions/0007-owner-presence-first))

:::note Bluetooth range is not a room
The owner in the next room may still count as present, and a watch left on the desk counts as
the owner. Bangle.js 1 cannot reliably tell whether it is being worn.
:::

## Listen

For a sensitive reminder with the microphone allowed, the robot listens for
`listen_window_minutes` (5 minutes). A voice-activity detector (Silero VAD) cuts the audio into
speech segments, and the speaker model (SpeechBrain ECAPA) turns each one into an embedding,
compared with the average of the owner's voice samples. A segment whose similarity is below
`identity.voice_threshold` may be someone else; one short segment is too little to tell, so a
voice becomes an **audio bystander** only once `identity.min_nonowner_seconds` (3 s) of its
speech is heard and that speech, taken together, still does not match the owner
([ADR 0013](/decisions/0013-voice-enrolment-and-pooled-voice-evidence)). Remembered bystanders
are recognised by voice too. With
the ask-once policy, the voice of someone the owner allowed before is only noted: the robot
listens on, and then still scans for silent people. It stops listening once it hears someone it
must ask about, or someone the owner declined for.

## Scan

If nobody else was heard and the camera is allowed, the head sweeps the room for silent
bystanders **until the due time** (the last 2 minutes): level, then up, then down, looking
**right, front and left**; each next row starts from the side where the head already is, so it
only nods between rows, again and again. Each face found by InsightFace is
compared with the owner's face and with remembered bystanders (`identity.face_threshold`). A
face that does not clearly match the owner is **looked at closer** before the sweep goes on:
several views, averaged, decide who it is; with **following** on, the head also turns and nods
towards it until it is in full view. Someone the owner allowed before is noted and the sweep goes
on; once it finds someone it must ask about, or someone the owner declined for, it stops. If the
due time comes first, it found no one (or only people allowed before)
([ADR 0012](/decisions/0012-scan-until-due)).

The robot also scans when it heard only the owner (`reminder.scan_if_only_owner_heard`), because
a silent person may still be in the room.

## Decide

One pure function, `domain/policy.py:decide`, makes the call. It is tested exhaustively.

| Situation | Decision |
|---|---|
| Not sensitive, or policy *always say it* | **Speak** |
| Detection *neither* | **Ask** on the watch (the robot cannot know who is there) |
| Nobody else found | **Speak** |
| Someone found, policy *always ask* | **Ask** |
| Someone found, *ask once*, any of them answered *no* before | **Watch** |
| Someone found, *ask once*, all of them answered *yes* before | **Speak** |
| Someone found, *ask once*, someone unknown | **Ask** |

## Consent

The watch buzzes and shows *"I noticed someone is with you. Should I say your reminder out
loud?"* with Yes and No. **No answer within 60 seconds counts as no** and is never remembered.
With the *ask once* policy, a Yes or No is stored with the bystander's anonymous label (`B-001`)
and embedding, so the robot does not ask about that person again.

## Deliver

The reminder is delivered **at the due time**, never early
([ADR 0004](/decisions/0004-deliver-at-due-time)): either out loud, with lip-synced speech from
the Ohbot, or privately on the watch as a *Private note*. Any error on the way (a crashed model,
an unreachable device, a missing enrolment) moves the flow to `FAILED` and sends the reminder to
the watch: the robot **fails closed** ([ADR 0003](/decisions/0003-fail-closed)).

:::privacy What the robot keeps from all this
Embeddings and labels, never frames or audio. The research log records state changes, scores and
answers as labels and numbers; reminder titles never enter it. See the
[privacy model](/reference/privacy).
:::

## Related topics

- [The reminder state machine](/reference/state-machine), state by state
- [Watch the pipeline on Home](/dashboard/home)
- [Tune thresholds](/research/calibration) and [swap models](/research/algorithms)
