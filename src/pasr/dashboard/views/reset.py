from __future__ import annotations

import streamlit as st

from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.state import get_handle, offline, settings
from pasr.paths import resolve
from pasr.storage.reset import reset

st.title("Reset")
st.markdown(
    """
A reset **always** deletes:
- all remembered bystanders and their embeddings,
- all remembered consent answers,
- your preferences (every setting returns to its default).

You choose whether the **owner** is deleted too , name, face and voice embeddings, and reminders.
"""
)

handle = get_handle()
with st.container(border=True):
    delete_owner = st.radio(
        "Also delete the owner's face and voice data?",
        [False, True],
        format_func=lambda yes: (
            "Yes , delete the owner and their reminders too"
            if yes
            else "No , keep the owner and their reminders"
        ),
    )
    purge_log = st.checkbox("Also delete the research event log (it holds no personal content)")
    st.divider()
    confirmed = st.checkbox("I understand this cannot be undone")
    if handle.running:
        st.caption("The robot will be stopped first.")
    reset_now = st.button(
        "Reset", type="primary", disabled=not confirmed, icon=":material/restart_alt:"
    )

if reset_now:
    if handle.running:
        with working("Stopping the robot"):
            handle.stop()
    data = offline()
    summary = reset(
        data.db,
        resolve(settings().storage.data_dir),
        delete_owner=delete_owner,
        purge_log=purge_log,
    )
    st.session_state.clear()
    notify(
        "Reset done. Deleted "
        + ", ".join(
            f"{n} {table.replace('_', ' ')} row(s)" for table, n in summary.deleted_rows.items()
        )
        + ("; settings restored to defaults." if summary.settings_cleared else "."),
        "success",
    )
    rerun()  # a fresh page, and the header shows the stopped robot
