from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from pasr.apps.reminder.capture import LONGEST_S, CaptureResult
from pasr.apps.reminder.service import DATE_QUESTION, ReminderDraft
from pasr.dashboard.components import study
from pasr.dashboard.components.confirm import confirm
from pasr.dashboard.components.forms import text_form
from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.components.robot import needs_running
from pasr.dashboard.components.tables import with_flags
from pasr.dashboard.state import (
    ago,
    attempt,
    get_handle,
    now,
    offline,
    on_robot,
    running,
    settings,
)
from pasr.domain.enums import ReminderOrigin, ReminderStatus
from pasr.domain.models import Reminder
from pasr.domain.timing import LATE_LISTEN_SHARE
from pasr.orchestration.runtime import Runtime

SENSITIVITY = {"Decide automatically": None, "Sensitive": True, "Not sensitive": False}

st.title("Reminders")
st.caption(
    "Sensitive reminders (e.g. a doctor's appointment) are only said out loud when the owner "
    "is alone or has agreed on the watch."
)

handle = get_handle()


def service_call(fn):
    """Use the running robot's service (shared clock and scheduler) or the database directly."""
    if running():

        def run(runtime: Runtime):
            result = fn(runtime.service)
            runtime.reminders.poke()
            return result

        return on_robot(run)
    return fn(offline().service)


def save_draft(draft: ReminderDraft, sensitive: bool | None) -> Reminder:
    """On the robot the sensitivity model runs off its event loop (``ReminderApp.save``)."""
    if running():

        async def save(runtime: Runtime) -> Reminder:
            return await runtime.reminders.save(
                draft, origin=ReminderOrigin.DASHBOARD, sensitive=sensitive
            )

        return handle.call(save, timeout=120)
    return offline().service.save(draft, origin=ReminderOrigin.DASHBOARD, sensitive=sensitive)


def saved(reminder: Reminder) -> None:
    kind = "sensitive" if reminder.sensitive else "not sensitive"
    notify(f"Saved #{reminder.id} for {reminder.due_at:%a %d %b %H:%M} ({kind}).", "success")
    st.session_state.pop("draft", None)
    rerun()


# Tracked, so the voice tab (and its "start the robot" toast) only renders while it is open.
add_text, add_test, add_voice = st.tabs(
    ["Type a reminder", "Quick test", "By voice"], key="add-reminder", on_change="rerun"
)

with add_text:
    with text_form("new-reminder"):
        text = st.text_input(
            "What should I remind you about?", placeholder="Doctor's appointment at 2pm tomorrow"
        )
        choice = st.selectbox("Sensitivity", list(SENSITIVITY))
        submitted = st.form_submit_button("Add reminder", type="primary")
    if submitted and text.strip():
        draft = attempt("Reading the reminder", lambda: service_call(lambda s: s.draft(text)))
        if draft is not None:
            st.session_state["draft"] = (draft, SENSITIVITY[choice])
    if pending := st.session_state.get("draft"):
        draft, sensitive = pending
        assert isinstance(draft, ReminderDraft)
        default_time = settings().reminder.default_time
        when = draft.time or f"{default_time:%H:%M} (no time given)"
        with st.container(border=True):
            st.caption("Check the reminder before saving it")
            st.write(f"**{draft.title}** · {draft.date or 'no date yet'} · {when}")
            if draft.needs_date:
                answer = st.date_input(DATE_QUESTION, value=date.today() + timedelta(days=1))
                draft = ReminderDraft(draft.title, answer, draft.time)
            with st.container(horizontal=True, gap="small"):
                save = st.button("Save", type="primary", icon=":material/check:")
                cancel = st.button("Cancel")
        if save:
            ready: ReminderDraft = draft
            with working("Saving the reminder"):
                reminder = attempt("Saving the reminder", lambda: save_draft(ready, sensitive))
            if reminder is not None:
                saved(reminder)
        if cancel:
            st.session_state.pop("draft", None)
            st.rerun()

with add_test:
    reminder_settings = settings().reminder
    st.caption(
        "A reminder due in a few seconds, to watch the whole pipeline. If it is sensitive, the "
        "robot starts at once. Due in under "
        f"{reminder_settings.wake_lead_minutes:g} minutes, with the microphone and camera, it "
        f"listens for the first {LATE_LISTEN_SHARE:.0%} of the time left (at least "
        f"{reminder_settings.min_listen_seconds:.0f} s) and scans the room in the rest."
    )
    with text_form("test-reminder"):
        title = st.text_input("Title", value="Doctor appointment", placeholder="A title")
        sensitive = st.toggle("Sensitive", value=True)
        with_media = st.toggle(study.LABEL, value=study.media(), help=study.HELP)
        seconds = st.number_input("Due in (seconds)", min_value=5, max_value=3600, value=45)
        if st.form_submit_button("Add test reminder", type="primary") and title.strip():
            study.save(with_media)  # before the run starts, which logs it
            due = now() + timedelta(seconds=int(seconds))
            reminder = attempt(
                "Adding the test reminder",
                lambda: service_call(
                    lambda service: service.create(
                        title, due, origin=ReminderOrigin.TEST, sensitive=sensitive
                    )
                ),
            )
            if reminder is not None:
                saved(reminder)

with add_voice:
    if add_voice.open and needs_running("set reminders by voice"):
        st.caption(
            "Press the button: the robot asks what to remind you about, then when, or at what "
            "time, if you did not say (a time alone is today, or tomorrow once it has passed). "
            "It asks each question up to three times. The audio and transcript are never stored."
        )
        if st.button("Talk to the robot", type="primary", icon=":material/mic:"):

            async def capture(runtime: Runtime) -> CaptureResult:
                return await runtime.reminders.capture_by_voice()

            with working("The robot is listening"):
                result = attempt("Listening", lambda: handle.call(capture, timeout=LONGEST_S))
            if result is not None and result.reminder is not None:
                saved(result.reminder)
            elif result is not None:
                notify(f"No reminder saved: {result.problem}", "warning")

st.subheader("All reminders")
show = st.segmented_control("Show", ["Upcoming", "All"], default="Upcoming")
data = offline()
reminders = data.service.upcoming() if show == "Upcoming" else data.repos.reminders.all()
if not reminders:
    st.caption("No reminders.")
else:
    reference = now()
    st.dataframe(
        with_flags(
            [
                {
                    "#": r.id,
                    "due": r.due_at.strftime("%a %d %b %Y %H:%M"),
                    "when": ago(r.due_at, reference),
                    "title": r.title,
                    "sensitive": r.sensitive,
                    "decided by": r.sensitivity_source,
                    "status": r.status.value.replace("_", " "),
                    "origin": r.origin.value,
                }
                for r in reminders
            ],
            "sensitive",
        ),
        hide_index=True,
        width="stretch",
    )
    titles = {r.id: r.title for r in reminders}
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        chosen = st.multiselect(
            "Select reminders to delete", list(titles), format_func=lambda i: f"#{i} {titles[i]}"
        )
        delete = confirm(
            "Delete selected",
            f"Deletes {len(chosen)} reminder(s): "
            + ", ".join(f"**#{i}** {titles[i]}" for i in chosen)
            + ". This cannot be undone.",
            key="delete-reminders",
            disabled=not chosen,
        )
    if delete:
        active = {r.id for r in data.repos.reminders.all([ReminderStatus.ACTIVE])}
        if active & set(chosen):
            notify("A reminder that is running right now cannot be deleted.", "error")
        else:
            for reminder_id in chosen:
                data.service.delete(reminder_id)
            notify(f"Deleted {len(chosen)} reminder(s).", "success")
            rerun()
