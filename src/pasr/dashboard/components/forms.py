"""A form whose button looks disabled, and cannot be clicked, until something is typed.

Streamlit only learns what was typed when the form is sent, so this is done in the browser: a
text box shows its placeholder exactly while it is empty, so the box needs a placeholder. A page
still ignores an empty form sent with the Enter key.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import streamlit as st

from pasr.dashboard.components.palette import colors

BOX = "pasr-text-form"


def styles() -> str:
    palette = colors()
    empty = f'[class*="st-key-{BOX}-"]:has([data-testid="stTextInput"] input:placeholder-shown)'
    return f"""
<style>
{empty} [data-testid="stFormSubmitButton"] button {{
  background: transparent; border-color: {palette["line"]}; color: {palette["disabled"]};
  pointer-events: none;
}}
{empty} [data-testid="stFormSubmitButton"] {{ cursor: not-allowed; }}
</style>
"""


@contextlib.contextmanager
def text_form(key: str, **options: bool) -> Iterator[None]:
    """``st.form(key)``, its button disabled while its text box is empty."""
    st.html(styles())
    with st.container(key=f"{BOX}-{key}"), st.form(key, **options):
        yield
