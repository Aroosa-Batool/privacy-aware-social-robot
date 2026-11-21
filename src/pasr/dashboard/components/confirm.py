"""Actions that delete something ask once more: the button opens a small panel that says what
will be lost, and only the red button inside it does it."""

from __future__ import annotations

from typing import Any

import streamlit as st

from pasr.dashboard.components.palette import colors

CONFIRM = "confirm"
PANEL = 320
"""px: the panel's width; a popover grows to fit what is in it, so a long consequence would
otherwise stretch it, and its red button, across the page."""


def styles() -> str:
    palette = colors()
    button = f'[class*="st-key-{CONFIRM}-"] button'
    return f"""
<style>
{button} {{
  background: {palette["danger"]}; border-color: {palette["danger"]}; color: #ffffff;
}}
{button}:hover:not(:disabled) {{
  background: {palette["danger_hover"]}; border-color: {palette["danger_hover"]}; color: #ffffff;
}}
{button}:focus-visible {{ outline: 2px solid {palette["danger"]}; outline-offset: 2px; }}
</style>
"""


def delete_button(label: str, *, key: str, **options: Any) -> bool:
    """The red button inside a confirm panel: the click that actually deletes."""
    st.html(styles())
    return st.button(label, key=f"{CONFIRM}-{key}", type="primary", **options)


def confirm(
    label: str,
    consequence: str,
    *,
    key: str,
    action: str | None = None,
    disabled: bool = False,
    icon: str = ":material/delete:",
) -> bool:
    """A ``label`` button that opens ``consequence`` and a red ``action`` button (default: the
    same words); True when that one is pressed."""
    with st.popover(label, icon=icon, disabled=disabled), st.container(width=PANEL):
        st.markdown(consequence)
        return delete_button(action or label, key=key, icon=icon, width="stretch")
