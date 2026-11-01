"""The Save and Discard buttons under a page of settings.

Every setting widget's key starts with the settings version: raising it after a save, a discard
or a loaded profile makes the widgets show the stored values again.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from pydantic import ValidationError

from pasr.dashboard.components.notify import notify, rerun
from pasr.dashboard.state import report_saved, save_settings
from pasr.settings.loader import diff

VERSION = "settings-version"


def settings_version() -> int:
    return int(st.session_state.setdefault(VERSION, 0))


def renew() -> None:
    """Show the stored values again in every setting widget."""
    st.session_state[VERSION] = settings_version() + 1


def leaves(changes: dict[str, Any]) -> int:
    return sum(leaves(value) if isinstance(value, dict) else 1 for value in changes.values())


def save_bar(edited: dict[str, Any], values: dict[str, Any]) -> None:
    """Save the settings in ``edited`` that differ from the stored ``values``, or discard them."""
    changes = diff(edited, values)
    st.divider()
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        save = st.button("Save", type="primary", disabled=not changes, icon=":material/save:")
        discard = st.button("Discard", disabled=not changes)
        st.caption(f"{leaves(changes)} unsaved change(s)" if changes else "No changes")
    if save:
        try:
            restart = save_settings(changes)
        except (ValidationError, ValueError) as exc:
            notify(f"Not saved: {exc}", "error")
        else:
            renew()
            report_saved("Settings saved.", restart)
            rerun()
    if discard:
        renew()
        st.rerun()
