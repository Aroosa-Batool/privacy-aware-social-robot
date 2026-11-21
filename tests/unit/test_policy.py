import itertools

import pytest

from pasr.domain.enums import DetectionModality as M
from pasr.domain.enums import DisclosurePolicy as P
from pasr.domain.policy import Decision, decide, requires_detection

SPEAK, ASK, WATCH = Decision.SPEAK, Decision.ASK_CONSENT, Decision.SEND_TO_WATCH
AUDIO, BOTH = M.AUDIO_ONLY, M.AUDIO_AND_CAMERA


@pytest.mark.parametrize(
    ("policy", "modality", "bystanders", "remembered", "expected"),
    [
        # no sensors: nobody can be detected, so the robot asks every time
        (P.ALWAYS_ASK, M.NONE, [], {}, ASK),
        (P.ASK_ONCE_PER_BYSTANDER, M.NONE, [], {}, ASK),
        # owner alone
        (P.ALWAYS_ASK, AUDIO, [], {}, SPEAK),
        (P.ALWAYS_ASK, M.CAMERA_ONLY, [], {}, SPEAK),
        (P.ASK_ONCE_PER_BYSTANDER, BOTH, [], {}, SPEAK),
        # the camera alone finds bystanders like any sensor
        (P.ALWAYS_ASK, M.CAMERA_ONLY, ["b"], {}, ASK),
        (P.ASK_ONCE_PER_BYSTANDER, M.CAMERA_ONLY, ["b"], {"b": True}, SPEAK),
        # always ask ignores anything remembered
        (P.ALWAYS_ASK, BOTH, ["b"], {}, ASK),
        (P.ALWAYS_ASK, BOTH, ["b"], {"b": True}, ASK),
        # ask once: remembered answers are reused
        (P.ASK_ONCE_PER_BYSTANDER, AUDIO, ["b"], {}, ASK),
        (P.ASK_ONCE_PER_BYSTANDER, AUDIO, ["b"], {"b": True}, SPEAK),
        (P.ASK_ONCE_PER_BYSTANDER, AUDIO, ["b"], {"b": False}, WATCH),
        (P.ASK_ONCE_PER_BYSTANDER, BOTH, ["a", "b"], {"a": True}, ASK),
        (P.ASK_ONCE_PER_BYSTANDER, BOTH, ["a", "b"], {"a": True, "b": True}, SPEAK),
        (P.ASK_ONCE_PER_BYSTANDER, BOTH, ["a", "b"], {"a": True, "b": False}, WATCH),
        (P.ASK_ONCE_PER_BYSTANDER, BOTH, ["a", "b"], {"b": False}, WATCH),  # a known "no" wins
    ],
)
def test_sensitive_decisions(policy, modality, bystanders, remembered, expected):
    decision = decide(
        policy=policy,
        modality=modality,
        sensitive=True,
        bystanders=bystanders,
        remembered=remembered,
    )
    assert decision is expected


@pytest.mark.parametrize(("policy", "modality"), list(itertools.product(P, M)))
def test_non_sensitive_is_always_spoken(policy, modality):
    decision = decide(
        policy=policy, modality=modality, sensitive=False, bystanders=["b"], remembered={"b": False}
    )
    assert decision is SPEAK


@pytest.mark.parametrize("modality", list(M))
def test_always_disclose_speaks_even_with_bystanders(modality):
    decision = decide(
        policy=P.ALWAYS_DISCLOSE,
        modality=modality,
        sensitive=True,
        bystanders=["b"],
        remembered={"b": False},
    )
    assert decision is SPEAK


@pytest.mark.parametrize(
    ("policy", "modality", "sensitive"), list(itertools.product(P, M, [True, False]))
)
def test_detection_only_for_sensitive_checked_reminders(policy, modality, sensitive):
    expected = sensitive and policy is not P.ALWAYS_DISCLOSE and modality is not M.NONE
    assert requires_detection(policy=policy, modality=modality, sensitive=sensitive) is expected


def test_each_detection_says_which_sensors_it_uses():
    assert [(m.value, m.listens, m.looks) for m in M] == [
        ("none", False, False),
        ("audio_only", True, False),
        ("camera_only", False, True),
        ("audio_and_camera", True, True),
    ]
