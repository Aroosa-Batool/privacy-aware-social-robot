"""Choosing a similarity threshold from measured scores.

*Genuine* scores compare the owner's fresh samples with the enrolled set; *impostor* scores do
the same for other people. Both are computed exactly as ``identity.identify`` does at runtime
(``identity.similarity`` with the configured aggregate), so the suggested threshold means the
same thing in the flow as it did in calibration. Only numbers are handled here; the embeddings
of other people never leave the capture step.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from pasr.domain.identity import Aggregate, ModelMismatchError, similarity
from pasr.domain.models import Embedding

MIN_GENUINE = 5
"""Fewer owner samples than this give an unreliable estimate."""
MARGIN = 0.10
"""Without impostor scores: how far below the owner's 10th percentile the threshold goes."""
GOOD_EER = 0.05
FAIR_EER = 0.15


class Verdict(StrEnum):
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    p10: float
    median: float

    @classmethod
    def of(cls, scores: Sequence[float]) -> ScoreSummary:
        if not scores:
            return cls(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        a = np.asarray(scores, dtype=np.float64)
        return cls(
            len(a),
            float(a.min()),
            float(a.max()),
            float(a.mean()),
            float(np.percentile(a, 10)),
            float(np.median(a)),
        )


@dataclass(frozen=True, slots=True)
class Calibration:
    genuine: ScoreSummary
    impostor: ScoreSummary | None
    suggested: float
    eer: float | None
    """Equal error rate at ``suggested``; ``None`` without impostor scores."""
    far_at_suggested: float | None
    """Share of impostor scores accepted at ``suggested``."""
    frr_at_suggested: float
    """Share of genuine scores rejected at ``suggested``."""
    verdict: Verdict
    notes: tuple[str, ...]


def histogram(
    scores: Sequence[float], bins: int = 20, lo: float = -1.0, hi: float = 1.0
) -> tuple[list[float], list[int]]:
    """``(lower bin edges, counts)`` over ``[lo, hi]``."""
    edges = np.linspace(lo, hi, bins + 1)
    counts, _ = np.histogram(np.asarray(scores, dtype=np.float64), bins=edges)
    return [float(e) for e in edges[:-1]], [int(c) for c in counts]


def scores_against(
    probes: Sequence[Embedding], enrolled: Sequence[Embedding], aggregate: Aggregate
) -> list[float]:
    """Each probe's similarity to the enrolled set, as ``identify`` would compute it."""
    scores = []
    for probe in probes:
        score = similarity(probe, enrolled, aggregate)
        if score is None:
            raise ModelMismatchError(probe.model, {e.model for e in enrolled})
        scores.append(score)
    return scores


def _rates(
    threshold: float, genuine: Sequence[float], impostor: Sequence[float]
) -> tuple[float, float]:
    far = float(np.mean([s >= threshold for s in impostor])) if impostor else 0.0
    frr = float(np.mean([s < threshold for s in genuine]))
    return far, frr


def calibrate(
    genuine: Sequence[float],
    impostor: Sequence[float] | None = None,
    *,
    margin: float = MARGIN,
    ceiling: float | None = None,
) -> Calibration:
    """``ceiling`` (the plugin's recommended threshold) caps the suggestion without impostor
    scores: the owner's scores show how low the threshold may go, never how high. Above the
    owner's typical scores it would only turn the owner into a stranger."""
    if not genuine:
        raise ValueError("calibration needs at least one owner score")
    g = [float(s) for s in genuine]
    i = [float(s) for s in impostor] if impostor else []
    g_summary, i_summary = ScoreSummary.of(g), ScoreSummary.of(i) if i else None
    notes: list[str] = []

    eer: float | None
    far: float | None
    if i_summary is not None:
        if i_summary.maximum < g_summary.minimum:  # separable: sit in the middle of the gap
            suggested = (i_summary.maximum + g_summary.minimum) / 2
        else:  # the threshold where false accepts and false rejects balance; ties → safer
            best: tuple[float, float] | None = None
            for candidate in sorted(set(g) | set(i)):
                gap = abs(np.subtract(*_rates(candidate, g, i)))
                if best is None or gap < best[0] or (gap == best[0] and candidate > best[1]):
                    best = (float(gap), candidate)
            assert best is not None
            suggested = best[1]
        far, frr = _rates(suggested, g, i)
        eer = (far + frr) / 2
        if i_summary.count < MIN_GENUINE:
            notes.append(
                f"only {i_summary.count} sample(s) of other people: the false-accept estimate "
                "is rough; capture more"
            )
    else:
        suggested = float(np.clip(g_summary.p10 - margin, -1.0, 1.0))
        far, eer = None, None
        if ceiling is not None and suggested > ceiling:
            suggested = ceiling
            notes.append(
                f"no samples of other people: the threshold stays at the model's recommended "
                f"{ceiling:.2f}, well below the owner's scores; capture another person to "
                "measure how high it may go"
            )
        else:
            notes.append(
                "no samples of other people: the threshold is a conservative margin below the "
                "owner's 10th percentile; capture another person for a real estimate"
            )
        _, frr = _rates(suggested, g, i)

    if g_summary.count < MIN_GENUINE:
        verdict = Verdict.INSUFFICIENT
        notes.insert(0, f"only {g_summary.count} owner sample(s); capture at least {MIN_GENUINE}")
    elif eer is None:
        verdict = Verdict.FAIR
    elif eer < GOOD_EER:
        verdict = Verdict.GOOD
    elif eer < FAIR_EER:
        verdict = Verdict.FAIR
    else:
        verdict = Verdict.POOR
        notes.append(
            "owner and others overlap a lot: more enrolment samples, a quieter room / better "
            "light, or a stronger plugin may be needed"
        )
    return Calibration(
        g_summary, i_summary, float(suggested), eer, far, float(frr), verdict, tuple(notes)
    )
