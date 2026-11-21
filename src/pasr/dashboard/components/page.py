"""Every page's place in the window: a column in the middle, at most ``WIDTH`` wide with room at
its sides, and, in a window wider than that, a frame around what the page shows. The header bar
above it spans the window (``header``)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import streamlit as st

from pasr.dashboard.components.palette import colors

WIDTH = 76
"""rem: the widest a page gets, its side padding included; a wider window leaves room at both
sides."""
SIDES = "clamp(1rem, 4vw, 3rem)"
"""Room at each side of a page, and of the bar's contents: less on a phone, more on a wide
screen."""
FRAME = "pasr-page"


def styles() -> str:
    palette = colors()
    return f"""
<style>
/* the page scrolls up and down only: the bar's overflow past the window's edge (a scroll bar's
   width) is clipped */
[data-testid="stMain"] {{ overflow-x: hidden; }}
[data-testid="stMainBlockContainer"] {{
  box-sizing: border-box; max-width: {WIDTH}rem; margin-left: auto; margin-right: auto;
  padding-left: {SIDES}; padding-right: {SIDES};
}}
@media (min-width: {WIDTH}rem) {{  /* room for a frame; a phone shows the page edge to edge */
  .st-key-{FRAME} {{
    border: 1px solid {palette["line"]}; border-radius: 0.6rem;
    padding: 0.5rem clamp(1.25rem, 2.5vw, 2.5rem) 2rem;
  }}
}}
</style>
"""


@contextlib.contextmanager
def frame() -> Iterator[None]:
    """What a page shows, framed (style-only HTML takes no space)."""
    st.html(styles())
    with st.container(key=FRAME):
        yield
