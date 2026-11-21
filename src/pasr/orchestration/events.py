"""Typed runtime events with a privacy check on every payload.

Events feed the dashboard and the research event log. They must never contain personal content
(reminder titles, transcripts, embeddings, images): payload keys are allow-listed and values
must be short scalars. A violation raises at the emit call, so tests catch it.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pasr.orchestration.clock import Clock

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    RUNTIME_STARTED = "runtime.started"
    RUNTIME_STOPPED = "runtime.stopped"
    FLOW_STARTED = "flow.started"
    FLOW_STATE = "flow.state"
    FLOW_ERROR = "flow.error"
    OWNER_PRESENCE = "owner.presence"
    VOICE_IDENTIFIED = "perception.voice"
    VOICE_POOLED = "perception.voice_pooled"
    FACE_IDENTIFIED = "perception.face"
    FACE_STUDIED = "perception.face_studied"
    ROOM_SCANNED = "perception.scan"
    CONSENT_REQUESTED = "consent.requested"
    CONSENT_ANSWERED = "consent.answered"
    CONSENT_REVOKED = "consent.revoked"
    BYSTANDER_ENROLLED = "bystander.enrolled"
    REMINDER_CREATED = "reminder.created"
    REMINDER_DELIVERED = "reminder.delivered"
    REMINDER_MISSED = "reminder.missed"
    OWNER_ENROLLED = "owner.enrolled"
    OWNER_ENROLMENT_FAILED = "owner.enrolment_failed"
    FACE_POSE_CAPTURED = "owner.face_pose"
    THRESHOLD_CALIBRATED = "identity.calibrated"
    SETTINGS_CHANGED = "settings.changed"


PayloadValue = str | int | float | bool | None

ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "answer",
        "channel",
        "count",
        "decision",
        "direction",
        "error_type",
        "face_model",
        "face_threshold",
        "faces",
        "frames",
        "identity",
        "late_seconds",
        "level",
        "modality",
        "mode",
        "no_face",
        "origin",
        "plugin",
        "policy",
        "pose",
        "present",
        "ready",
        "reason",
        "samples",
        "seconds",
        "sensitive",
        "sensitivity_model",
        "several",
        "similarity",
        "speaker_model",
        "tested_with",
        "threshold",
        "tilt",
        "turned",
        "unusable",
        "vad_model",
        "voice_threshold",
    }
)
MAX_STRING_LENGTH = 80


class PrivacyViolationError(ValueError):
    pass


def check_payload(data: Mapping[str, object]) -> None:
    for key, value in data.items():
        if key not in ALLOWED_PAYLOAD_KEYS:
            raise PrivacyViolationError(f"event payload key {key!r} is not allow-listed")
        if value is not None and not isinstance(value, str | int | float | bool):
            raise PrivacyViolationError(f"event payload {key!r} must be a scalar")
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise PrivacyViolationError(f"event payload {key!r} is too long to be a label")


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    ts: datetime
    session_id: str
    reminder_id: int | None = None
    bystander_id: str | None = None
    state_from: str | None = None
    state_to: str | None = None
    data: Mapping[str, PayloadValue] = field(default_factory=dict)


Sink = Callable[[Event], None]


class EventBus:
    def __init__(
        self, clock: Clock, session_id: str, sinks: list[Sink] | None = None, keep: int = 500
    ) -> None:
        self.clock = clock
        self.session_id = session_id
        self._sinks: list[Sink] = list(sinks or [])
        self.recent: deque[Event] = deque(maxlen=keep)

    def subscribe(self, sink: Sink) -> Callable[[], None]:
        self._sinks.append(sink)
        return lambda: self._sinks.remove(sink)

    def emit(
        self,
        type: EventType,
        *,
        reminder_id: int | None = None,
        bystander_id: str | None = None,
        state_from: str | None = None,
        state_to: str | None = None,
        **data: PayloadValue,
    ) -> Event:
        check_payload(data)
        event = Event(
            type=type,
            ts=self.clock.now(),
            session_id=self.session_id,
            reminder_id=reminder_id,
            bystander_id=bystander_id,
            state_from=state_from,
            state_to=state_to,
            data=data,
        )
        self.recent.append(event)
        for sink in list(self._sinks):
            try:
                sink(event)
            except Exception:  # an event sink must never break the robot
                logger.exception("recording the %s event failed", event.type.value)
        return event
