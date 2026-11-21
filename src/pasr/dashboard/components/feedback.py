"""The owner's feedback on a reminder's run through the pipeline, for comparing models: did it
work as it should (thumbs up or down) and, if not, what went wrong (optional, in their words).
It is saved with the models and settings the run used, from its ``flow.started`` event; the
comment never enters the event log (ADR 0014)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import streamlit as st

from pasr.dashboard.components import study
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.state import attempt, humanize, offline
from pasr.orchestration.clock import local_now
from pasr.storage.repos import Feedback, Run

QUESTION = "Did this run work as it should?"
WENT_WRONG = "What went wrong? (optional)"
DID_NOT_WORK = 0  # st.feedback's thumbs down; thumbs up is 1
MODELS = {  # the condition keys that name a model, in the order shown
    "speaker_model": "speaker",
    "vad_model": "VAD",
    "face_model": "face",
    "sensitivity_model": "sensitivity",
}


def verdict(worked: bool) -> str:
    return "worked well" if worked else "did not work well"


def outcome(run: Run) -> str:
    """How the run ended, in words."""
    went = {"spoken": "spoken", "watch": "sent to the watch"}.get(run.channel or "", "missed")
    if run.state == "DONE":
        return went
    if run.state == "FAILED":
        return f"failed, {went}"
    return f"unfinished, last at {humanize(run.state).lower()}"


def models(run: Run) -> str:
    """What the run was tested with, and the models, thresholds and privacy choices it used."""
    condition = run.condition
    if not condition:
        return "Its models were not logged: it ran before the robot logged them."
    tested = condition.get("tested_with")
    named = [f"{label} {condition[key]}" for key, label in MODELS.items() if key in condition]
    return (
        (f"Tested with {study.WORDS[tested]}. " if tested in study.WORDS else "")
        + f"Ran with {', '.join(named)}; thresholds voice {condition.get('voice_threshold')}, "
        f"face {condition.get('face_threshold')}; detection {humanize(condition.get('mode'))}, "
        f"policy {humanize(condition.get('policy'))}."
    )


def rate(session_id: str, reminder_id: int) -> None:
    """What the run was tested with and used; thumbs up or down on it, what went wrong with a
    thumbs down, and Save."""
    repos = offline().repos
    saved = repos.feedback.get(session_id, reminder_id)
    # the log's run, or the copy kept with the feedback once the log has been purged
    run = repos.events.run(session_id, reminder_id) or (saved.run if saved else None)
    if run is not None:
        st.caption(models(run))
    key = f"feedback-{session_id}-{reminder_id}"
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown(QUESTION, width="content")
        thumbs = st.feedback(
            "thumbs", key=f"{key}-worked", default=None if saved is None else int(saved.worked)
        )
    comment = ""
    if thumbs == DID_NOT_WORK:
        comment = st.text_area(
            WENT_WRONG,
            value=saved.comment if saved else "",
            key=f"{key}-comment",
            max_chars=2000,
            placeholder="For example: it took my own voice for someone else's.",
        )
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        save = st.button(
            "Save feedback", key=f"{key}-save", disabled=thumbs is None, icon=":material/check:"
        )
        st.caption(
            f"Saved {saved.rated_at:%a %d %b %H:%M}: {verdict(saved.worked)}."
            if saved
            else "Not rated yet."
        )
    if not save or thumbs is None:
        return
    if run is None:  # neither logged nor rated: the log was purged while the page was open
        notify(f"Reminder #{reminder_id}'s run is no longer in the event log.", "error")
        return
    worked = thumbs != DID_NOT_WORK
    stored = attempt(
        "Saving the feedback",
        lambda: repos.feedback.save(run, worked=worked, comment=comment.strip(), now=local_now()),
    )
    if stored is not None:
        notify(f"Saved: reminder #{reminder_id}'s run {verdict(worked)}.", "success")
        rerun()


def rows(feedback: Sequence[Feedback]) -> list[dict[str, Any]]:
    """One row per rated run, with the run's condition as columns, for the table and export."""
    return [
        {
            "session": item.run.session_id,
            "reminder": item.run.reminder_id,
            "started": item.run.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "state": item.run.state,
            "channel": item.run.channel,
            "worked": item.worked,
            "comment": item.comment,
            "rated": item.rated_at.strftime("%Y-%m-%d %H:%M:%S"),
            **item.run.condition,
        }
        for item in feedback
    ]
