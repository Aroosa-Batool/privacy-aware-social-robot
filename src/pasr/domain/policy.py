"""The disclosure decision , the core privacy rule of the reminder app, as a pure function."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from pasr.domain.enums import DetectionModality, DisclosurePolicy


class Decision(StrEnum):
    SPEAK = "speak"
    ASK_CONSENT = "ask_consent"
    SEND_TO_WATCH = "send_to_watch"


def requires_detection(
    *, policy: DisclosurePolicy, modality: DetectionModality, sensitive: bool
) -> bool:
    """Whether the robot must wake up early and look for bystanders before the reminder."""
    return (
        sensitive
        and policy is not DisclosurePolicy.ALWAYS_DISCLOSE
        and modality is not DetectionModality.NONE
    )


def decide(
    *,
    policy: DisclosurePolicy,
    modality: DetectionModality,
    sensitive: bool,
    bystanders: Sequence[str],
    remembered: Mapping[str, bool],
) -> Decision:
    """Decide how to deliver a reminder.

    ``bystanders`` are the ids of everyone other than the owner that detection found.
    ``remembered`` maps bystander ids to the owner's earlier answer (only used with
    ``ASK_ONCE_PER_BYSTANDER``).
    """
    if not sensitive or policy is DisclosurePolicy.ALWAYS_DISCLOSE:
        return Decision.SPEAK
    if modality is DetectionModality.NONE:
        # Without sensors the robot cannot know who is present, so it always asks.
        return Decision.ASK_CONSENT
    if not bystanders:
        return Decision.SPEAK
    if policy is DisclosurePolicy.ALWAYS_ASK:
        return Decision.ASK_CONSENT

    answers = [remembered.get(b) for b in bystanders]
    if any(a is False for a in answers):
        return Decision.SEND_TO_WATCH
    if all(a is True for a in answers):
        return Decision.SPEAK
    return Decision.ASK_CONSENT
