---
title: Profile and enrolment
nav: Profile
description: Register the robot's owner, teach it their face and voice, make the privacy choices, and save or load every setting as a profile.
---

The robot keeps only face and voice **embeddings** (lists of numbers), never photos or
recordings. A progress bar at the top shows how much of the profile is complete.

::image src=/assets/media/profile.webp alt="The Profile page: Owner, Face and Voice steps marked Done, with Capture face and Capture voice buttons." url=localhost:8501/profile caption="All three enrolment steps done, each tagged with the model that made its samples."

:::steps
@step Owner

Type the owner's name and click **Save name**. The name is shown on the dashboard and used in the
robot's own speech; it never enters the research log.

@step Face

Click **Capture face** with the robot running, sit **alone** in front of the head camera, about
an arm's length away, and do what the robot says: look straight at its camera, turn your head
about halfway to your left and to your right, then tilt your chin up and down. It keeps 4
images of each pose (`identity.enroll_face_samples`), half a second apart, and uses a frame only
when your face is in full view and points the asked way. When a pose does not come it says what
is wrong ("Please come a little closer to me", "The other way, please"), and at the end it asks
once more for each pose it missed. Each pose gets at most 15 seconds
(`identity.enroll_face_pose_seconds`); the whole capture takes about half a minute.

The robot tells you how it went. With the straight-ahead pose it stores your face, and names any
pose it could not see (the page then says how many of the 20 images it stored; capture again to
add the rest). Without it, nothing is stored, and the robot says why and asks you to try again.
The page shows the number of samples and the model that made them, for example
`insightface-buffalo_l`. **Delete face data** removes them.

If one pose keeps failing, the `owner.face_pose` events on the Events page say why; the pose can
also be left out of `identity.enroll_face_poses`. See
[ADR 0011](/decisions/0011-guided-face-enrolment).

@step Voice

Click **Capture voice** and speak naturally for about 12 seconds, about your day for example,
until enough speech segments are in (`identity.enroll_voice_samples`, 3), recorded with
`speechbrain-spkrec-ecapa-voxceleb` by default. **Delete voice data** removes them.

@step Your privacy choices

Three questions, saved with **Save preferences**.
:::

::image src=/assets/media/profile-privacy.webp alt="The privacy choices: how the robot may check for other people, how to handle sensitive reminders, and whether to remember watch answers." url=localhost:8501/profile

## The privacy choices

**How may the robot check whether someone else is in the room?** (`privacy.detection_modality`)

| Choice | Value | What it means |
|---|---|---|
| Microphone only | `audio_only` | The camera is never used for this. |
| Camera only | `camera_only` | The microphone is never used for this (setting a reminder by voice still uses it). |
| Microphone and camera | `audio_and_camera` | Listen first, then look around (the default). |
| Neither | `none` | No detection; with a sensitive reminder the robot always asks on the watch. |

**How should the robot handle sensitive reminders when someone else may hear them?**

- *Always say them out loud, whoever is present* (`always_disclose`)
- *Ask me on the watch when someone else is present* (`always_ask` by default)

**When you answer on the watch, should the robot remember it for that person?** Shown when you
choose to be asked.

- *Don't remember*: ask every time, and keep nothing about the person (`always_ask`).
- *Remember*: keep the answer with that person's face and voice embeddings, and don't ask about
  them again (`ask_once_per_bystander`). Remembered people are listed under
  [People & consent](/dashboard/people), where you can forget them.

:::privacy Changing a model means enrolling again
Embeddings from different models cannot be compared. If you switch the face or speaker model on
[Models](/dashboard/models), the robot refuses to match against the old embeddings (it fails
closed) until you capture face or voice again, and you should [re-calibrate](/research/calibration).
:::

## Profiles: save or load all settings

A profile is a YAML file with every setting, useful to repeat an experiment or to switch between
study conditions. In the **Profiles** section, download the current settings, or upload a profile
and click **Apply profile**. From a terminal:

```bash
uv run pasr config dump > my-condition.yaml
uv run pasr run --profile my-condition.yaml
```

See [Study conditions](/research/profiles).

## From a terminal

```bash
uv run pasr setup                       # owner, face, voice, the two questions
uv run pasr setup --no-face             # voice only
uv run pasr setup --name "Ada" --modality audio_only --policy ask_once_per_bystander
uv run pasr setup --live-view           # watch the samples come in
```
