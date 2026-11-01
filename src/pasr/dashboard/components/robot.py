"""The robot's state (a rippling dot while it runs), the live view switch and the start / stop
buttons: always in the header bar. A page that needs the robot running says so once, in a toast;
one that needs it stopped also has a button that stops it right there."""

from __future__ import annotations

from typing import Any, Literal

import streamlit as st

from pasr.dashboard.components.loading import working
from pasr.dashboard.components.notify import notify
from pasr.dashboard.components.palette import colors
from pasr.dashboard.state import attempt, get_handle, save_settings, settings

Action = Literal["start", "stop"]
WORDS: dict[Action, str] = {"start": "Starting the robot", "stop": "Stopping the robot"}


def perform(action: Action, *, where: Any = None) -> None:
    """Start or stop with the moving dots in ``where``; a failure stays on the page as a
    warning, anything else reloads it with the new state."""
    handle = get_handle()
    run = {"start": handle.start, "stop": handle.stop}[action]
    with working(WORDS[action], where=where):
        attempt(WORDS[action], run)
    if action == "stop" or handle.running:
        st.rerun()


def state_styles() -> str:
    palette = colors()
    ring = "content: ''; position: absolute; inset: 0; border-radius: 50%; background: inherit"
    return f"""
<style>
.pasr-state {{
  display: inline-flex; align-items: center; gap: 0.55rem; height: 1.9rem;
  padding: 0 0.8rem 0 0.7rem; border-radius: 999px; font-size: 0.9rem; font-weight: 600;
  white-space: nowrap;
}}
.pasr-state.is-running {{ background: {palette["ok"]}1f; color: {palette["ok"]}; }}
.pasr-state.is-stopped {{ background: {palette["line"]}; color: {palette["bar_text"]}; }}
.pasr-state-dot {{
  position: relative; width: 0.6rem; height: 0.6rem; border-radius: 50%; background: currentColor;
}}
/* while the robot runs, rings ripple out of the dot, one after the other */
.is-running .pasr-state-dot::before, .is-running .pasr-state-dot::after {{
  {ring}; animation: pasr-ripple 1.8s ease-out infinite;
}}
.is-running .pasr-state-dot::after {{ animation-delay: 0.9s; }}
@keyframes pasr-ripple {{
  from {{ transform: scale(1); opacity: 0.55; }}
  to {{ transform: scale(3.2); opacity: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{  /* a slow glow instead of moving rings */
  .is-running .pasr-state-dot::before, .is-running .pasr-state-dot::after {{ animation: none; }}
  .is-running .pasr-state-dot {{ animation: pasr-glow 2.4s ease-in-out infinite; }}
  @keyframes pasr-glow {{ 50% {{ opacity: 0.35; }} }}
}}
</style>
"""


def state(running: bool) -> str:
    """The robot's state as a pill: a dot and a word, the dot rippling while it runs."""
    word = "Running" if running else "Stopped"
    return (
        f'<span class="pasr-state is-{word.lower()}" role="status">'
        f'<span class="pasr-state-dot" aria-hidden="true"></span>{word}</span>'
    )


def controls() -> Action | None:
    """The state, and only the buttons that apply to it; returns the one pressed."""
    running = get_handle().running
    with st.container(
        key="pasr-robot", horizontal=True, width="content", gap="small", vertical_alignment="center"
    ):
        st.html(state_styles() + state(running), width="content")
        if not running:
            started = st.button(
                "Start robot", type="primary", icon=":material/play_arrow:", key="robot-start"
            )
            return "start" if started else None
        stop = st.button("Stop", icon=":material/stop_circle:", key="robot-stop")
        return "stop" if stop else None


def live_view_switch() -> None:
    """Whether the robot opens the live view window on the laptop; saved, so it lasts."""
    saved = settings().live_view.enabled
    switched = st.toggle(
        "Live view window",
        value=saved,
        help="While the robot listens, scans, enrols or calibrates, open a window on this "
        "laptop with the camera frames it analyses (each face labelled owner or someone else), "
        "the microphone level and each voice match. Nothing is stored, but people nearby appear "
        "on screen.",
    )
    if switched != saved:
        save_settings({"live_view": {"enabled": not saved}})


def needs_running(purpose: str) -> bool:
    """True if the robot runs; otherwise a toast that it must run to ``purpose``, with Start
    robot in the header bar."""
    if get_handle().running:
        return True
    notify(  # not again on every reload or refresh
        f"The robot is stopped. Start it at the top right to {purpose}.", "warning", once=True
    )
    return False


def needs_stopped(purpose: str, *, key: str) -> bool:
    """True if the robot is stopped; otherwise a toast that it must stop to ``purpose`` (while
    it runs it owns the devices), and a button that stops it right here."""
    if not get_handle().running:
        return True
    message = f"The robot is running and using the devices. Stop it to {purpose}."
    notify(message, "warning", once=True)  # not again on every reload or refresh
    pressed = st.button("Stop the robot", icon=":material/stop_circle:", key=key, help=message)
    status = st.container()  # the moving dots appear under the button
    if pressed:
        perform("stop", where=status)
    return False
