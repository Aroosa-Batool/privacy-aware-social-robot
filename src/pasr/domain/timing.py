from __future__ import annotations

from datetime import datetime, timedelta

LATE_LISTEN_SHARE = 0.7
"""A flow that started late and may also use the camera listens for this share of the time
left; the camera gets the rest, so a silent bystander is still looked for before the due time."""

ON_TIME_SLACK = timedelta(seconds=1)
"""A flow that starts on time wakes a few milliseconds after its start time; that is not late."""


def flow_start(due: datetime, *, wake_lead: timedelta, needs_detection: bool) -> datetime:
    """When the reminder flow starts: early for bystander detection, otherwise at the due time."""
    return due - wake_lead if needs_detection else due


def started_late(woke: datetime, due: datetime, *, wake_lead: timedelta) -> bool:
    """The flow woke with less than its wake-up lead left: a quick test, a reminder added
    shortly before it is due, or a robot started late."""
    return due - woke < wake_lead - ON_TIME_SLACK


def listen_deadline(
    start: datetime,
    due: datetime,
    *,
    window: timedelta,
    min_listen: timedelta,
    until_due: bool,
    share: float = 1.0,
) -> datetime:
    """End of the listening window.

    ``share`` of the time left before the due time is the most it listens for, so that a late
    flow leaves time to scan the room. Listening never runs past the due time unless the flow
    started late, in which case it still listens for ``min_listen`` , privacy wins over
    punctuality.
    """
    end = due if until_due else min(start + window, start + (due - start) * share)
    return max(end, start + min_listen)


def is_missed(due: datetime, now: datetime, *, grace: timedelta) -> bool:
    return now > due + grace
