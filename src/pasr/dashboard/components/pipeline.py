"""The reminder pipeline as a strip of stages, highlighting where the current flow is.

Each stage says its state in words as well as colour and a mark, so it reads the same for
colour-blind viewers and screen readers: done ✓ in green; ! in amber where something kept the
reminder from being said out loud (the owner away, a bystander declined before, a "no" or no
answer on the watch, the owner gone by the due time); failed ✕ in red; now in blue; skipped or
not reached in grey. A green stage that found or decided something says what (someone heard or
seen, a "yes"), and Deliver says where the reminder went. Arrows give the direction. The route
taken is green, dashed amber or red where it leaves an amber or red stage; where the flow
skipped stages it arches over them instead of running through them.

A flow that fails is marked at the stage it failed in. The reminder then goes to the watch
(fail closed), so Deliver shows whether it got there. While the robot runs, a failure is also a
red toast on whatever page is open, with what went wrong (``alerts``)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import streamlit as st

from pasr.apps.reminder.due_flow import DueState
from pasr.dashboard.components.palette import colors
from pasr.domain.enums import DeliveryChannel, WatchAnswer
from pasr.orchestration.notices import sentence
from pasr.orchestration.runtime import FlowView

S = DueState
DELIVER = "Deliver"
DELIVERING = {S.WAIT_FOR_DUE, S.DISCLOSE_SPEAK, S.DISCLOSE_WATCH, S.DONE}
STAGES: list[tuple[str, set[DueState]]] = [
    ("Schedule", {S.IDLE}),
    ("Wake", {S.WAKING}),
    ("Presence", {S.CHECKING_PRESENCE, S.OWNER_AWAY}),
    ("Listen", {S.LISTENING, S.AUDIO_BYSTANDER}),
    ("Scan", {S.SCANNING, S.VISUAL_BYSTANDER}),
    ("Decide", {S.NO_BYSTANDER, S.CHECK_MEMORY}),
    ("Consent", {S.AWAITING_CONSENT}),
    (DELIVER, DELIVERING),
]

Progress = Literal["done", "turned", "now", "failed", "pending"]
WORDS: dict[Progress, str] = {
    "done": "done",
    "now": "now",
    "failed": "failed",
    "pending": "not reached",
}
MARKS: dict[Progress, str] = {"done": "✓", "turned": "!", "failed": "✕"}


@dataclass(frozen=True, slots=True)
class Stage:
    name: str
    progress: Progress
    word: str
    """What happened there; shown, and not only read out, unless the stage is plainly done
    or was not reached."""
    why: str = ""
    """What it found or decided, for the summary line."""


def styles() -> str:
    palette = colors()
    arrow = "border-top: 5px solid transparent; border-bottom: 5px solid transparent"
    routes = "".join(  # the way on from an amber or a red stage: dashed, in its colour
        f"""
.pasr-step.is-taken.via-{kind}::before {{
  background: repeating-linear-gradient(90deg, {color} 0 6px, transparent 6px 10px);
}}
.pasr-step.is-taken.via-{kind}::after, .via-{kind} .pasr-step-bypass::after {{
  border-left-color: {color};
}}
.via-{kind} .pasr-step-bypass {{ border-color: {color}; border-style: dashed; }}"""
        for kind, color in (("turned", palette["warn"]), ("failed", palette["danger"]))
    )
    return f"""
<style>
.pasr-steps-box {{ container-type: inline-size; }}
.pasr-steps {{  /* equal columns, so an arch over n stages is n columns wide */
  list-style: none; margin: 0.25rem 0 0.5rem; padding: 1rem 0 0;
  display: grid; grid-template-columns: repeat({len(STAGES)}, minmax(0, 1fr)); row-gap: 1rem;
}}
.pasr-step {{
  position: relative; display: flex; flex-direction: column; align-items: center;
  gap: 0.2rem; padding: 0 0.3rem; margin: 0; text-align: center;
}}
.pasr-step::before {{  /* the line from the previous stage */
  content: ""; position: absolute; top: 0.95rem; right: 50%; width: 100%; height: 2px;
  background: {palette["line"]};
}}
.pasr-step::after {{  /* its arrow, half-way along */
  content: ""; position: absolute; left: 0; top: calc(0.95rem + 1px);
  transform: translate(-50%, -50%); border-left: 7px solid {palette["line"]}; {arrow};
}}
.pasr-step:first-child::before, .pasr-step:first-child::after {{ display: none; }}
.pasr-step.is-taken::before {{ background: {palette["ok"]}; }}
.pasr-step.is-taken::after {{ border-left-color: {palette["ok"]}; }}
.pasr-step-bypass {{  /* from the last stage reached, over the skipped ones, to this one */
  position: absolute; right: 50%; width: calc(var(--over) * 100%);
  top: -0.85rem; height: 1.8rem;
  border: 2px solid {palette["ok"]}; border-bottom: 0; border-radius: 0.9rem 0.9rem 0 0;
}}
.pasr-step-bypass::after {{
  content: ""; position: absolute; left: 50%; top: -1px;
  transform: translate(-50%, -50%); border-left: 7px solid {palette["ok"]}; {arrow};
}}{routes}
.pasr-step-mark {{  /* over the lines, which pass behind a stage that was skipped */
  position: relative; z-index: 1; width: 1.9rem; height: 1.9rem; border-radius: 50%;
  display: grid; place-items: center; font-size: 0.85rem; font-weight: 700;
  border: 2px solid {palette["line"]}; background: {palette["page"]}; color: {palette["muted"]};
}}
.is-done .pasr-step-mark {{
  background: {palette["ok"]}; border-color: {palette["ok"]}; color: #fff;
}}
.is-turned .pasr-step-mark {{  /* amber, and the ! and the words say it without colour */
  background: {palette["warn"]}; border-color: {palette["warn"]}; color: #fff;
}}
.is-now .pasr-step-mark {{
  background: {palette["accent"]}; border-color: {palette["accent"]}; color: #fff;
  animation: pasr-step-ping 1.6s ease-out infinite;
}}
.is-failed .pasr-step-mark {{  /* red, and the ✕ and the word say it without colour */
  background: {palette["danger"]}; border-color: {palette["danger"]}; color: #fff;
}}
.pasr-step-name {{ font-weight: 600; font-size: 0.9rem; }}
.is-pending .pasr-step-name {{ color: {palette["muted"]}; }}
.pasr-step-state {{
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
}}
.is-done .pasr-step-state {{ color: {palette["ok"]}; }}
.is-turned .pasr-step-state {{ color: {palette["warn"]}; }}
.is-now .pasr-step-state {{ color: {palette["accent"]}; }}
.is-failed .pasr-step-state {{ color: {palette["danger"]}; }}
.is-quiet .pasr-step-state {{  /* read out, not shown */
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%);
}}
@keyframes pasr-step-ping {{
  0% {{ box-shadow: 0 0 0 0 {palette["accent"]}80; }}
  80%, 100% {{ box-shadow: 0 0 0 0.55rem {palette["accent"]}00; }}
}}
@container (max-width: 40rem) {{  /* too narrow for one row: stages wrap, without lines */
  .pasr-steps {{
    grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr)); padding-top: 0;
  }}
  .pasr-step::before, .pasr-step::after, .pasr-step-bypass {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{ .is-now .pasr-step-mark {{ animation: none; }} }}
</style>
"""


def progress(states: set[DueState], visited: set[DueState], current: DueState | None) -> Progress:
    if current in states:
        return "done" if current is S.DONE else "now"
    return "done" if visited & states else "pending"


def failed_at(flow: FlowView) -> DueState | None:
    """The state a failed flow was in when the error came; None if it did not fail."""
    if flow.state != S.FAILED.value or len(flow.steps) < 2:
        return None
    return DueState(flow.steps[-2][0])


def stage_of(state: DueState) -> str:
    return next(name for name, states in STAGES if state in states)


def outcome(name: str, flow: FlowView, visited: set[DueState]) -> Stage | None:
    """What the stage ``name``, done, found or decided, if worth saying: amber when it kept the
    reminder from being said out loud, green when the flow went on as usual (a bystander found
    is detection working; whether it matters is for Decide and Consent)."""
    if name == "Presence" and S.OWNER_AWAY in visited:
        why = "the owner's watch did not answer, so the owner counted as away"
        return Stage(name, "turned", "away", why)
    if name == "Listen" and S.AUDIO_BYSTANDER in visited:
        return Stage(name, "done", "heard someone", "someone other than the owner was heard")
    if name == "Scan" and S.VISUAL_BYSTANDER in visited:
        return Stage(name, "done", "saw someone", "someone other than the owner was seen")
    if name == "Decide" and S.CHECK_MEMORY in visited and S.AWAITING_CONSENT not in visited:
        if flow.planned == DeliveryChannel.WATCH:
            why = "the owner had declined for them before"
            return Stage(name, "turned", "declined before", why)
        return Stage(name, "done", "allowed before", "the owner had allowed them before")
    if name == "Consent" and flow.answer == WatchAnswer.YES:
        return Stage(name, "done", "said yes", "the owner said yes on the watch")
    if name == "Consent" and flow.answer == WatchAnswer.NO:
        return Stage(name, "turned", "said no", "the owner said no on the watch")
    if name == "Consent" and flow.answer == WatchAnswer.TIMEOUT:
        return Stage(name, "turned", "no answer", "the owner did not answer on the watch")
    return None


def delivery(flow: FlowView, visited: set[DueState], failed: DueState | None) -> Stage:
    """Deliver: where the reminder went. Once the flow failed, the reminder goes to the watch
    (fail closed): it got there (amber if Deliver itself failed first), is on its way (at the
    due time), or was missed."""
    left = flow.planned == DeliveryChannel.SPOKEN and S.DISCLOSE_WATCH in visited
    why = "at the due time the owner's watch did not answer, so it was not said out loud"
    if failed is not None:
        if flow.delivered:
            turned = failed in DELIVERING
            return Stage(DELIVER, "turned" if turned else "done", "to watch", why if left else "")
        if not flow.finished:
            return Stage(DELIVER, "now", WORDS["now"], why if left else "")
        return Stage(DELIVER, "failed", "missed", why if left else "")
    where = progress(DELIVERING, visited, DueState(flow.state))
    if where != "done":
        return Stage(DELIVER, where, WORDS[where])
    if flow.delivered == DeliveryChannel.SPOKEN:
        return Stage(DELIVER, "done", "spoken")
    if left:  # the owner went out of range while the robot waited
        return Stage(DELIVER, "turned", "owner left", why)
    return Stage(DELIVER, "done", "to watch")


def stages(flow: FlowView | None) -> list[Stage]:
    """Each stage: how far the flow got there, and what happened."""
    if flow is None:
        return [Stage(name, "pending", WORDS["pending"]) for name, _ in STAGES]
    visited = {DueState(step[0]) for step in flow.steps}
    current = DueState(flow.state)
    failed = failed_at(flow)
    found = []
    for name, states in STAGES:
        if name == DELIVER:
            found.append(delivery(flow, visited, failed))
        elif failed is not None and failed in states:
            found.append(Stage(name, "failed", WORDS["failed"]))
        else:
            where = progress(states, visited, current)
            said = outcome(name, flow, visited) if where == "done" else None
            found.append(said or Stage(name, where, WORDS[where]))
    last = max((i for i, stage in enumerate(found) if stage.progress != "pending"), default=-1)
    return [  # grey before the last stage reached: skipped, not still to come
        replace(stage, word="skipped") if stage.progress == "pending" and i < last else stage
        for i, stage in enumerate(found)
    ]


def went(flow: FlowView, failed: DueState) -> str:
    """What became of a failed reminder: the watch takes it (fail closed), and if it failed on
    the watch itself, the robot tries the watch again."""
    again = failed is S.DISCLOSE_WATCH
    if not flow.finished:
        return "The robot tries the watch again." if again else "It goes to the watch."
    if flow.delivered:
        return "It reached the watch on a second try." if again else "It was sent to the watch."
    if again:
        return "Trying the watch again failed too, so it was missed."
    return "The watch could not be reached either, so it was missed."


def summary(flow: FlowView) -> str:
    """The flow in a line: what its stages found or decided, and where it went, or where it
    failed and what became of it."""
    said = [f"{stage.why}." for stage in stages(flow) if stage.why]
    failed = failed_at(flow)
    if failed is not None:
        said += [
            f"the {stage_of(failed)} step failed.",
            sentence(flow.problem or ""),
            went(flow, failed),
        ]
    elif flow.finished:
        spoken = flow.delivered == DeliveryChannel.SPOKEN
        said.append("it was spoken." if spoken else "it was sent to the watch.")
    else:
        said.insert(0, "running.")
    text = " ".join(part[:1].upper() + part[1:] if i else part for i, part in enumerate(said))
    return f"last run: {text}" if flow.finished else text


def problems(flow: FlowView) -> list[str]:
    """One toast each: the failure (the same words from start to end, so it shows once), and a
    reminder that then could not reach the watch either."""
    failed = failed_at(flow)
    if failed is None:
        return []
    then = (
        "The robot tries the watch again."
        if failed is S.DISCLOSE_WATCH
        else "The reminder goes to the watch."
    )
    found = [
        f"Reminder #{flow.reminder_id}: the {stage_of(failed)} step failed. "
        f"{sentence(flow.problem or '')} {then}"
    ]
    if flow.finished and not flow.delivered:
        found.append(f"Reminder #{flow.reminder_id} could not be sent to the watch: missed.")
    return found


def strip(flow: FlowView | None) -> str:
    """The stages as HTML: a stage's line from the previous one is coloured when the flow went
    that way, in the colour of the stage it came from; one reached after skipped stages gets an
    arch from the last stage reached."""
    found = stages(flow)
    items = []
    last = None  # the last stage reached so far
    for index, stage in enumerate(found):
        where = stage.progress
        reached = where != "pending"
        classes = f"pasr-step is-{where}"
        if where == "pending" or stage.word == WORDS["done"]:  # nothing more to say
            classes += " is-quiet"
        if reached and last is not None and found[last].progress in ("turned", "failed"):
            classes += f" via-{found[last].progress}"
        if reached and last == index - 1:
            classes += " is-taken"
        bypass = ""
        if reached and last is not None and last < index - 1:
            bypass = (
                f'<span class="pasr-step-bypass" style="--over: {index - last}" '
                'aria-hidden="true"></span>'
            )
        if reached:
            last = index
        mark = MARKS.get(where, str(index + 1))
        current_step = ' aria-current="step"' if where == "now" else ""
        items.append(
            f'<li class="{classes}"{current_step}>{bypass}'
            f'<span class="pasr-step-mark" aria-hidden="true">{mark}</span>'
            f'<span class="pasr-step-name">{stage.name}</span>'
            f'<span class="pasr-step-state">{stage.word}</span></li>'
        )
    return (
        '<div class="pasr-steps-box"><ol class="pasr-steps" aria-label="Reminder pipeline">'
        f"{''.join(items)}</ol></div>"
    )


def pipeline_strip(flow: FlowView | None) -> None:
    st.html(styles() + strip(flow))


def flow_steps(flow: FlowView) -> None:
    rows = [
        {"state": state, "at": at.strftime("%H:%M:%S"), "why": reason}
        for state, at, reason in flow.steps
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
