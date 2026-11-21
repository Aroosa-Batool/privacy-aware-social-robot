"""Toasts, on whatever page is open, for what goes wrong while the robot runs: a reminder's
pipeline that fails (red, and again if the reminder then misses the watch too), and every
problem the robot reports along the way (``orchestration.notices``): a camera that dropped off
USB and is being reconnected, a watch that did not answer, an error nothing else caught. Each
shows once; what happened before the dashboard was opened is old news."""

from __future__ import annotations

import time

import streamlit as st

from pasr.dashboard.components.notify import notify
from pasr.dashboard.components.pipeline import problems
from pasr.dashboard.state import get_handle

OPENED = "pasr-alerts-opened"  # when this session began
SEEN = "pasr-alerts-seen"  # the last robot notice shown
OLD_FLOW = "pasr-alerts-old-flow"  # the flow that had already ended when this session first looked


@st.fragment(run_every="2s")
def alerts() -> None:
    opened = st.session_state.setdefault(OPENED, time.time())
    handle = get_handle()
    if not handle.running:
        return
    seen = st.session_state.get(SEEN, 0)
    try:
        flow, notices = handle.call_sync(
            lambda runtime: (runtime.latest_flow(), runtime.notices.since(seen))
        )
    except Exception:  # the robot is busy or stopping; the next refresh tries again
        return
    for notice in notices:
        if notice.at >= opened:
            notify(notice.message, notice.kind)
    if notices:
        st.session_state[SEEN] = notices[-1].id
    old = st.session_state.setdefault(
        OLD_FLOW, flow.reminder_id if flow is not None and flow.finished else None
    )
    if flow is not None and flow.reminder_id != old:
        for message in problems(flow):
            notify(message, "error", once=True)
