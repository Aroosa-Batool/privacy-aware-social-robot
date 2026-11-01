"""Shared dashboard state: one robot runtime per Streamlit server, plus database access.

The runtime lives in a background thread (``RuntimeHandle``) so page re-runs never restart it.
When it is stopped, pages read and write the database directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import streamlit as st

from pasr.dashboard.components.notify import notify
from pasr.orchestration.clock import local_now
from pasr.orchestration.handle import RuntimeHandle
from pasr.orchestration.notices import describe
from pasr.orchestration.offline import Offline, open_offline
from pasr.orchestration.runtime import Runtime
from pasr.settings.loader import load_settings, update_overrides
from pasr.settings.schema import Settings

logger = logging.getLogger(__name__)


@st.cache_resource
def get_handle() -> RuntimeHandle:
    return RuntimeHandle(load_settings)


def settings() -> Settings:
    return load_settings()


def offline() -> Offline:
    return open_offline(load_settings(), session_id="dashboard")


def running() -> bool:
    return get_handle().running


def on_robot[T](fn: Callable[[Runtime], T]) -> T:
    """Run ``fn`` on the runtime thread (the runtime must be running)."""
    return get_handle().call_sync(fn)


def explain(exc: BaseException) -> str:
    """A short message for an error; the traceback goes to the terminal log."""
    if isinstance(exc, TimeoutError):
        return "the robot did not finish in time (it may still be working; see Home)"
    return describe(exc)


def attempt[T](what: str, action: Callable[[], T]) -> T | None:
    """Run one dashboard action. An error , a device that cannot be opened, a model that fails,
    a timeout , becomes a red toast instead of a crashed page; ``None`` is returned. The full
    traceback goes to the terminal log."""
    try:
        return action()
    except Exception as exc:
        logger.exception("%s failed", what)
        notify(f"{what} failed: {explain(exc)}", "error")
        return None


def now() -> datetime:
    """The robot's clock when it runs, else the local time."""
    if not running():
        return local_now()
    try:
        return on_robot(lambda rt: rt.clock.now())
    except Exception:  # the robot is busy or stopping: the local time is close enough
        return local_now()


def save_settings(changes: dict[str, Any]) -> list[str]:
    """Persist setting changes and apply them to the running robot.

    Returns the settings groups that only take effect after a restart.
    """
    update_overrides(settings().storage.data_dir, changes)
    if not running():
        return []
    fresh = load_settings()
    try:
        return on_robot(lambda rt: rt.apply_settings(fresh))
    except Exception as exc:  # saved, but the running robot could not take them live
        logger.exception("applying settings to the running robot failed")
        notify(f"Saved, but the robot could not apply them now: {explain(exc)}", "warning")
        return sorted(changes)


def report_saved(message: str, restart: list[str]) -> None:
    """A toast that ``message`` is done, or a warning one when changes to the ``restart``
    groups wait for the robot to be stopped and started again."""
    if restart:
        notify(
            f"{message} Changes to {', '.join(restart)} apply once you stop and start the robot "
            "(at the top right).",
            "warning",
        )
    else:
        notify(message, "success")


def humanize(value: object) -> str:
    return str(getattr(value, "value", value)).replace("_", " ")


def ago(moment: datetime, reference: datetime) -> str:
    seconds = int((moment - reference).total_seconds())
    future, seconds = seconds >= 0, abs(seconds)
    if seconds < 90:
        text = f"{seconds} s"
    elif seconds < 5400:
        text = f"{seconds // 60} min"
    elif seconds < 172800:
        text = f"{seconds // 3600} h {seconds % 3600 // 60} min"
    else:
        text = f"{seconds // 86400} days"
    return f"in {text}" if future else f"{text} ago"
