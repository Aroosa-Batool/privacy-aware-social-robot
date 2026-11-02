from __future__ import annotations

from typing import Any, Literal

import streamlit as st

from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.components.robot import needs_running
from pasr.dashboard.components.score_chart import score_chart
from pasr.dashboard.state import attempt, get_handle, offline, on_robot, settings
from pasr.domain.calibration import MIN_GENUINE, Calibration, Verdict, calibrate
from pasr.domain.enums import Biometric
from pasr.orchestration.calibration import THRESHOLD_FIELDS
from pasr.orchestration.enrollment import face_enrolment_seconds
from pasr.orchestration.runtime import Runtime
from pasr.perception.registry import PluginKind, recommended_threshold
from pasr.settings.loader import load_settings

# Voice calibration takes more segments than enrolment: fewer than MIN_GENUINE give no verdict.
VOICE_SAMPLES = max(6, MIN_GENUINE)
VOICE_SECONDS = 60.0
KINDS = {Biometric.FACE: PluginKind.FACE, Biometric.VOICE: PluginKind.SPEAKER}
BadgeColor = Literal["green", "orange", "red", "gray"]
VERDICTS: dict[Verdict, tuple[str, BadgeColor, str]] = {
    Verdict.GOOD: ("Good: you and the others are far apart", "green", ":material/check_circle:"),
    Verdict.FAIR: ("Fair: you and the others are a little close", "orange", ":material/info:"),
    Verdict.POOR: ("Poor: you and the others overlap", "red", ":material/error:"),
    Verdict.INSUFFICIENT: ("Too few samples to judge", "gray", ":material/hourglass_empty:"),
}
# An illustration for the explanation, not anyone's data.
EXAMPLE_YOU = [0.62, 0.66, 0.69, 0.71, 0.72, 0.74, 0.75, 0.77, 0.78, 0.8, 0.81, 0.83, 0.86]
EXAMPLE_OTHERS = [-0.06, 0.0, 0.03, 0.06, 0.08, 0.11, 0.13, 0.15, 0.18, 0.21, 0.24, 0.29]
EXPLAINED = """
**What the robot does with a face or a voice.** Its model turns each face (or stretch of
speech) into a list of numbers and compares it with what it learned of you when you enrolled.
The answer is a **similarity**: close to 1 for the same picture, around 0 for someone unrelated.

**The threshold is a line on that scale.** At or above it the robot treats the person as
**you**; below it as **someone else**, and then it keeps sensitive reminders private.

- **Line too high:** the robot mistakes you for a stranger and keeps asking on the watch. With
  the face model, a person usually scores between about 0.6 and 0.9 against their own enrolment,
  so a line at 0.85 rejects them half of the time.
- **Line too low:** a stranger can be mistaken for you, and could hear a private reminder.

**Calibration puts the line where it belongs for your camera, microphone, room and model.** The
robot measures fresh samples of you and of other people, scored exactly as during a reminder,
and the line goes in the gap between the two groups. Only that one number is saved; the samples
are scored and forgotten.
"""
HOW_TO = """
**You need one or two other people, but never two people in view at once.** Frames with two
faces are not used.

1. **You**, alone in front of the robot.
2. **Then each other person**, alone, in the same seat, one at a time. They follow the same
   instructions. Their samples are only scored, never stored.
3. **Choose the line** and save it. The robot uses it right away.

Do it where you will use the robot: same seat, same light, about an arm's length away. Two
other people give a steadier result than one. Alone, the robot can only check that the line
sits below your own scores, so it keeps it at the model's recommended starting point at most.
"""

st.title("Calibration")
st.caption(
    "Measure how alike the robot finds you and other people, and draw the line between them. "
    "Do it after enrolling, and again after re-enrolling or changing a model."
)

current = settings()
identity = current.identity
handle = get_handle()
measured = st.session_state.setdefault("calibration", {})

# open until something is measured: then the steps below matter more
learning = not any(scores.get("owner") for scores in measured.values())
with st.expander("What is calibration?", icon=":material/school:", expanded=learning):
    st.markdown(EXPLAINED)
    st.altair_chart(
        score_chart(EXAMPLE_YOU, EXAMPLE_OTHERS, 0.45),
        alt="Illustration: your samples score 0.6 to 0.9, other people's below 0.3, and the line "
        "sits between them at 0.45",
    )
    st.caption(
        "An illustration, not your data: each dot is one sample, blue for you and orange for "
        "other people. Everything right of the line counts as you."
    )
with st.expander("How to do it", icon=":material/checklist:", expanded=learning):
    st.markdown(HOW_TO)

modality = st.segmented_control(
    "What to calibrate",
    list(Biometric),
    default=Biometric.FACE,
    required=True,
    format_func=lambda m: "Face" if m is Biometric.FACE else "Voice",
    key="calibration.modality",
)
field = THRESHOLD_FIELDS[modality]
now = float(getattr(identity, field))
plugin = current.perception.choice(KINDS[modality]).plugin
default = recommended_threshold(KINDS[modality], plugin)
st.caption(
    f"Threshold now: **{now:.2f}**"
    + (f" · the {plugin} model's recommended starting point: {default:.2f}" if default else "")
)

scores: dict[str, Any] = measured.setdefault(modality.value, {"owner": [], "others": []})
enrolled = offline().repos.owner.enrollment().get(modality, (0, []))[0]
if not enrolled:
    st.info(
        f"Enrol your {modality.value} on the Profile page first: calibration compares new "
        "samples with it.",
        icon=":material/person_add:",
    )
    st.stop()
ready = needs_running(f"calibrate the {modality.value} threshold")


def measure(person: str) -> list[float] | None:
    """Capture and score fresh samples of whoever is in front of the robot now."""
    if modality is Biometric.FACE:
        timeout = face_enrolment_seconds(identity) + 30

        def run(rt: Runtime) -> Any:
            return rt.calibration.score_face(
                samples=identity.enroll_face_samples, timeout_s=identity.enroll_face_pose_seconds
            )
    else:
        timeout = VOICE_SECONDS + 30

        def run(rt: Runtime) -> Any:
            return rt.calibration.score_voice(samples=VOICE_SAMPLES, timeout_s=VOICE_SECONDS)

    with working(f"Measuring {person}"):
        return attempt("Measuring", lambda: handle.call(run, timeout=timeout))


def step(number: int, title: str, done: bool) -> None:
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(f"#### {number} · {title}", width="content", anchors=False)
        if done:
            st.badge("Done", icon=":material/check:", color="green")


how = (
    "do what the robot says, as when you enrolled: look straight at it, then turn and tilt "
    "your head. It takes about half a minute"
    if modality is Biometric.FACE
    else f"talk for about half a minute, for example about your day, until {VOICE_SAMPLES} "
    "stretches of speech are in"
)

with st.container(border=True):
    step(1, "Measure yourself", bool(scores["owner"]))
    st.caption(f"Sit alone in front of the robot, click **Measure me**, then {how}.")
    if scores["owner"]:
        owner = scores["owner"]
        st.write(
            f"{len(owner)} samples of you · lowest {min(owner):.2f} · highest {max(owner):.2f}"
        )
    if st.button(
        "Measure me again" if scores["owner"] else "Measure me",
        type="secondary" if scores["owner"] else "primary",
        disabled=not ready,
        icon=":material/person:",
    ):
        samples = measure("you")
        if samples is not None:
            scores["owner"] = samples
            rerun()

with st.container(border=True):
    step(2, "Measure other people", bool(scores["others"]))
    st.caption(
        "Move out of view. One other person sits alone in the same seat and clicks **Measure "
        f"another person**, then does the same: {how}. Repeat for a second person."
    )
    for number, person in enumerate(scores["others"], start=1):
        st.write(f"Person {number}: {len(person)} samples · highest {max(person):.2f}")
    if st.button(
        "Measure another person",
        disabled=not ready or not scores["owner"],
        icon=":material/group_add:",
        help=None if scores["owner"] else "Measure yourself first.",
    ):
        samples = measure("the other person")
        if samples is not None:
            scores["others"].append(samples)
            rerun()

with st.container(border=True):
    step(3, "Choose the line and save it", False)
    if not scores["owner"]:
        st.caption("Your samples, and the line through them, appear here once you are measured.")
        st.stop()
    owner, others = scores["owner"], [s for person in scores["others"] for s in person]
    result: Calibration = calibrate(owner, others or None, ceiling=default)
    line = st.slider(
        "Threshold",
        min_value=0.0,
        max_value=1.0,
        value=round(result.suggested, 2),
        step=0.01,
        key=f"calibration.{modality.value}.line.{len(owner)}.{len(others)}",
        help="Starts at the suggested line. Move it to see who would count as you.",
    )
    st.altair_chart(
        score_chart(owner, others, line),
        alt=f"Your {len(owner)} samples and {len(others)} of other people, with the threshold "
        f"at {line:.2f}",
    )
    accepted = sum(score >= line for score in owner)
    mistaken = sum(score >= line for score in others)
    with st.container(horizontal=True):
        st.metric("Samples of you counted as you", f"{accepted} of {len(owner)}", border=True)
        st.metric(
            "Samples of others counted as you",
            f"{mistaken} of {len(others)}" if others else "not measured",
            border=True,
        )
        st.metric("Suggested line", f"{result.suggested:.2f}", border=True)
    label, color, icon = VERDICTS[result.verdict]
    st.badge(label, icon=icon, color=color)
    for note in result.notes:
        st.caption(note[:1].upper() + note[1:])
    with st.expander("The scores as a table"):
        st.dataframe(
            {
                "who": ["you"] * len(owner) + ["other people"] * len(others),
                "similarity": [round(s, 3) for s in owner + others],
            },
            alt="Every measured sample's similarity to your enrolment",
        )
    with st.container(horizontal=True):
        save = st.button(
            f"Save {line:.2f} as the {modality.value} threshold",
            type="primary",
            disabled=not ready,
            icon=":material/save:",
        )
        if st.button("Start over", icon=":material/restart_alt:"):
            measured.pop(modality.value, None)
            rerun()
    if save:

        def apply(rt: Runtime) -> list[str]:
            rt.calibration.apply(modality, line, result)
            return rt.apply_settings(load_settings())

        if attempt("Saving the threshold", lambda: on_robot(apply)) is not None:
            notify(f"Saved: the {modality.value} threshold is now {line:.2f}.", "success")
            rerun()
