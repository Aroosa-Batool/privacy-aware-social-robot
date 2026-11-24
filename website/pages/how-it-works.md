---
title: How it works
description: The eight stages every reminder goes through, from the moment it is added to the moment it is said out loud or shown privately on the watch.
---

Every reminder passes through the same eight stages, and the dashboard's **Home** page shows each
reminder as a row of them, so you can follow along as it runs. They are the stages of the
robot's state machine ([full diagram](/reference/state-machine)). This page walks through them in
order and explains why each one is there.

::pipeline

## Profile: the owner registers

Before anything else, the owner registers once, on the dashboard's [Profile](/dashboard/profile)
page or with `pasr setup`. The robot needs to know what the owner looks and sounds like, so it can
tell them apart from anyone else. It captures **embeddings** of the owner's face (4 images in each
of 5 poses) and voice (30 seconds of speech, first read aloud from a text on the screen and then in
their own words, stored as samples of about 4 seconds). It then asks two questions that decide how
it behaves from then on:

| Question | Choices | Setting |
|---|---|---|
| How may the robot check whether someone else is in the room? | microphone only · camera only · microphone and camera · neither | `privacy.detection_modality` |
| What should it do with a sensitive reminder when someone else may hear it? | always say it · ask on the watch every time · ask once per person and remember | `privacy.disclosure_policy` |

## Schedule

You can type a reminder on the dashboard, add it with `pasr reminder add`, or say it to the robot.
A spoken reminder is transcribed locally with faster-whisper, and the robot never keeps the audio
or the text of what you said. A time without a date means today, or tomorrow if that minute has
already passed.

When you say a reminder and leave out the time, the robot asks *When should I remind you?* or
*At what time should I remind you?*, each at most three times
([ADR 0015](/decisions/0015-asking-for-a-reminder-by-voice)). When you type one, it asks for a
missing date and uses `reminder.default_time` (midnight) for a missing time.

A **sensitivity** model then reads the title and decides whether it is private:
*doctor's appointment* is sensitive, *buy groceries* is not. The default is a zero-shot DeBERTa
model that checks the title against a list of topics (health, therapy, money, the police, a job
interview, a password, …); a keyword list is the lightweight alternative. You can always override
the decision by hand.

## Wake

The scheduler checks the database every 10 seconds, and a reminder's flow starts at its wake-up
time. How early that is depends on how much checking the reminder needs:

- **Sensitive and checked** (the policy is not *always say it* and detection is not *neither*):
  `wake_lead_minutes` before it is due (7 minutes by default). This gives the robot time to
  listen and then look around before the reminder is due.
- **Camera only:** only 2 minutes early. The robot does not listen, so it can wake later and go
  straight to the scan.
- **Not sensitive:** at the due time, because there is nothing to check.

If a reminder is added only a few minutes before it is due (a **Quick test**, for example), its
flow starts at once. With both the microphone and the camera allowed, the robot then splits the
time left: it listens for the first 70% (at least `min_listen_seconds`, 15 s) and scans in the
rest, so the scan still finishes before the due time.

## Presence

Before it uses the microphone or the camera, the robot **pings the owner's watch** over Bluetooth.
If the owner is not around, there is nothing to protect and no reason to sense the room: listening
or filming would only capture other people. The owner counts as present only if the watch answers
with the consent app loaded. If there is no answer, the watch is out of range, the app is not
loaded, or anything goes wrong, the owner counts as **away**. Then nothing is sensed, nothing is
said, and the reminder goes to the watch at its due time. The ping is repeated right before the
robot speaks, in case the owner has left in the meantime.
([ADR 0007](/decisions/0007-owner-presence-first))

:::note Bluetooth range is not a room
The owner in the next room may still count as present, and a watch left on the desk counts as
the owner. Bangle.js 1 cannot reliably tell whether it is being worn.
:::

## Listen

For a sensitive reminder, if the microphone is allowed, the robot listens for
`listen_window_minutes` (5 minutes). A voice-activity detector (Silero VAD) cuts the audio into
speech segments, and the speaker model (SpeechBrain ECAPA) turns each segment into an embedding,
which is compared with the average of the owner's voice samples. A segment whose similarity is
below `identity.voice_threshold` may belong to someone else.

One short segment is too little to judge a voice reliably, and judging on one segment made the
robot mistake its own owner for a stranger. So a voice only becomes an **audio bystander** once
`identity.min_nonowner_seconds` (3 s) of its speech has been heard and that speech, taken
together, still does not match the owner
([ADR 0013](/decisions/0013-voice-enrolment-and-pooled-voice-evidence)).

Remembered bystanders are recognised by voice too. Under the ask-once policy, the voice of
someone the owner allowed before is only noted: the robot keeps listening, and afterwards still
scans for silent people. It stops listening as soon as it hears someone it must ask about, or
someone the owner declined for, because one such person already settles the question.

## Scan

Not everyone in a room talks. So if nobody else was heard and the camera is allowed, the head
sweeps the room for silent bystanders **until the due time** (the last 2 minutes). It looks
**right, front and left** at three head heights: level, then up, then down. Each new row starts
from the side where the head already is, so between rows it only nods instead of swinging back
across the room, and it repeats the sweep until time runs out.

Each face that InsightFace finds is compared with the owner's face and with remembered bystanders
(`identity.face_threshold`). A single frame can be poor (blurred, cut off, turned away), so a face
that does not clearly match the owner is **looked at closer** before the sweep goes on: several
views are averaged to decide who it is. With **following** switched on, the head also turns and
nods towards the face until it is in full view.

Someone the owner allowed before is noted, and the sweep goes on. As soon as the robot finds
someone it must ask about, or someone the owner declined for, it stops. If the due time comes
first, it has found no one (or only people allowed before)
([ADR 0012](/decisions/0012-scan-until-due)).

The robot also scans when it heard only the owner (`reminder.scan_if_only_owner_heard`), because a
silent person may still be in the room.

## Decide

A single pure function, `domain/policy.py:decide`, makes the call from what was found and the
owner's two choices. Keeping the decision in one function with no side effects means it can be
tested exhaustively, and it is.

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

When the robot needs to ask, the watch buzzes and shows *"I noticed someone is with you. Should I
say your reminder out loud?"* with Yes and No buttons. **No answer within 60 seconds counts as
no**, and that silence is never remembered. Under the *ask once* policy, a Yes or No is stored with
the bystander's anonymous label (`B-001`) and embedding, so the robot does not ask about that
person again.

## Deliver

The reminder is delivered **at the due time**, never early, even if the owner answered the watch
minutes before ([ADR 0004](/decisions/0004-deliver-at-due-time)). It is either said out loud, with
lip-synced speech from the Ohbot, or shown privately on the watch as a *Private note*.

Any error on the way (a crashed model, an unreachable device, a missing enrolment) moves the flow
to `FAILED` and sends the reminder to the watch. In other words, when the robot is unsure, it
stays quiet: it **fails closed** ([ADR 0003](/decisions/0003-fail-closed)).

:::privacy What the robot keeps from all this
Embeddings and labels, never frames or audio. The research log records state changes, scores and
answers as labels and numbers; reminder titles never enter it. See the
[privacy model](/reference/privacy).
:::

## Related topics

- [The reminder state machine](/reference/state-machine), state by state
- [Watch the pipeline on Home](/dashboard/home)
- [Tune thresholds](/research/calibration) and [swap models](/research/algorithms)
