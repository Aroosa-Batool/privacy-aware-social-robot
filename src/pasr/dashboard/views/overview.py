from __future__ import annotations

import streamlit as st

from pasr.dashboard.components.notify import notify
from pasr.dashboard.components.pipeline import flow_steps, pipeline_strip, summary
from pasr.dashboard.components.tables import with_flags
from pasr.dashboard.state import ago, explain, get_handle, humanize, offline, settings
from pasr.orchestration.runtime import setup_warnings

handle = get_handle()
st.title("Home")  # the live view switch is in the header bar, on every page


def stopped_view() -> None:  # Start robot is in the header bar, so not repeated here
    data = offline()
    owner = data.repos.owner.get()
    enrolled = {m.value: n for m, (n, _) in data.repos.owner.enrollment().items()}
    warnings = setup_warnings(settings(), owner.display_name if owner else None, enrolled)
    if warnings:  # once per session, not on every refresh
        notify(
            "**Finish setting up**\n\n" + "\n".join(f"- {warning}" for warning in warnings),
            "warning",
            once=True,
        )
    upcoming = data.service.upcoming()[:5]
    if upcoming:
        st.subheader("Next reminders")
        st.dataframe(
            with_flags(
                [
                    {"due": r.due_at.strftime("%a %d %b %H:%M"), "sensitive": r.sensitive}
                    for r in upcoming
                ],
                "sensitive",
            ),
            hide_index=True,
        )


@st.fragment(run_every="1s")
def live_view() -> None:
    try:
        snapshot = handle.snapshot()
    except Exception as exc:  # the robot is busy or stopping; the next refresh tries again
        st.caption(f"Waiting for the robot… ({explain(exc)})")
        return
    if snapshot is None:
        stopped_view()
        return

    policy, detection, next_up = st.columns(3)
    policy.metric("Policy", humanize(snapshot.policy), border=True)
    detection.metric("Detection", humanize(snapshot.modality), border=True)
    if (up := snapshot.next_reminder) is not None:  # counted down on every refresh
        doing = (
            "the robot is on it now"
            if up.running
            else f"the robot starts preparing {ago(up.starts_at, snapshot.now)}"
        )
        next_up.metric(
            "Next reminder (test)" if up.test else "Next reminder",
            ago(up.due_at, snapshot.now) if up.due_at > snapshot.now else "due now",
            help=f"Reminder #{up.reminder_id}, due {up.due_at:%a %H:%M:%S}; {doing}.",
            border=True,
        )
    else:
        next_up.metric("Next reminder", "none", border=True)
    for warning in snapshot.warnings:
        notify(warning, "warning", once=True)

    flow = snapshot.active_flow or snapshot.last_flow
    st.subheader("Pipeline")
    if flow is None:
        st.caption("No reminder has run in this session yet.")
    else:
        st.caption(f"Reminder #{flow.reminder_id} , {summary(flow)}")
    pipeline_strip(flow)
    if flow is not None:
        with st.expander("Steps of this reminder", expanded=snapshot.active_flow is not None):
            flow_steps(flow)

    st.subheader("Recent events")
    rows = [
        {
            "time": event.ts.strftime("%H:%M:%S"),
            "event": event.type.value,
            "reminder": event.reminder_id,
            "change": f"{event.state_from} → {event.state_to}" if event.state_to else "",
            "details": ", ".join(f"{k}={v}" for k, v in event.data.items() if v is not None),
        }
        for event in reversed(snapshot.events[-15:])
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(f"Robot clock: {snapshot.now:%a %d %b %H:%M:%S} · session {snapshot.session_id}")


live_view()
