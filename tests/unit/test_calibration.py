import numpy as np
import pytest

from pasr.domain.calibration import (
    MIN_GENUINE,
    ScoreSummary,
    Verdict,
    calibrate,
    histogram,
    scores_against,
)
from pasr.domain.identity import Aggregate, ModelMismatchError
from pasr.domain.models import Embedding


def test_separable_sets_put_the_threshold_in_the_gap():
    result = calibrate([0.8, 0.85, 0.9, 0.95, 0.99], [0.1, 0.2, 0.3])
    assert result.suggested == pytest.approx((0.3 + 0.8) / 2)
    assert result.eer == 0 and result.far_at_suggested == 0 and result.frr_at_suggested == 0
    assert result.verdict is Verdict.GOOD
    assert any("only 3 sample(s) of other people" in n for n in result.notes)


def test_overlapping_sets_balance_the_error_rates():
    genuine = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    impostor = [0.3, 0.4, 0.55, 0.65, 0.75]
    result = calibrate(genuine, impostor)
    assert 0.55 <= result.suggested <= 0.8
    assert result.eer is not None and result.eer == pytest.approx(
        (result.far_at_suggested + result.frr_at_suggested) / 2
    )
    assert result.verdict in (Verdict.FAIR, Verdict.POOR)


def test_suggestion_balances_false_accepts_and_false_rejects():
    genuine = [0.55, 0.6, 0.62, 0.7, 0.8, 0.9]
    impostor = [0.3, 0.5, 0.58, 0.61, 0.75]
    result = calibrate(genuine, impostor)

    def gap(threshold: float) -> float:
        far = np.mean([s >= threshold for s in impostor])
        frr = np.mean([s < threshold for s in genuine])
        return abs(far - frr)

    candidates = sorted(set(genuine) | set(impostor))
    assert result.suggested in candidates
    assert gap(result.suggested) == pytest.approx(min(gap(t) for t in candidates))
    assert result.far_at_suggested == pytest.approx(
        np.mean([s >= result.suggested for s in impostor])
    )


def test_without_impostors_a_margin_below_the_owner_is_used():
    result = calibrate([0.80, 0.82, 0.85, 0.90, 0.95, 0.97])
    assert result.impostor is None and result.eer is None and result.far_at_suggested is None
    assert result.suggested == pytest.approx(result.genuine.p10 - 0.10)
    assert result.verdict is Verdict.FAIR
    assert "no samples of other people" in result.notes[0]


def test_without_impostors_the_owner_alone_never_raises_it_above_the_model_default():
    # near-copies of one view score very high: p10 - 0.10 would be about 0.85, and then the
    # owner seen from the side or in other light would count as a stranger
    owner = [0.95, 0.96, 0.96, 0.97, 0.98]
    assert calibrate(owner, ceiling=0.40).suggested == 0.40
    assert "model's recommended 0.40" in calibrate(owner, ceiling=0.40).notes[0]
    low = [0.40, 0.42, 0.45, 0.50, 0.55]  # below the default: the margin under the owner wins
    assert calibrate(low, ceiling=0.40).suggested == pytest.approx(calibrate(low).suggested)
    assert calibrate(owner, [0.1, 0.2], ceiling=0.40).suggested > 0.40  # others measured


def test_too_few_owner_samples_is_insufficient():
    result = calibrate([0.9] * (MIN_GENUINE - 1), [0.1] * 10)
    assert result.verdict is Verdict.INSUFFICIENT
    assert result.notes[0].startswith(f"only {MIN_GENUINE - 1} owner sample")
    with pytest.raises(ValueError):
        calibrate([])


def test_summary_and_histogram():
    summary = ScoreSummary.of([0.0, 0.5, 1.0])
    assert (summary.count, summary.minimum, summary.maximum, summary.median) == (3, 0, 1, 0.5)
    assert ScoreSummary.of([]).count == 0
    edges, counts = histogram([-1.0, 0.0, 0.05, 0.99, 1.0], bins=4)
    assert edges == [-1.0, -0.5, 0.0, 0.5] and counts == [1, 0, 2, 2]


def test_scores_against_matches_identify_and_refuses_other_models():
    enrolled = [Embedding.of([1, 0], "m"), Embedding.of([0.9, 0.1], "m")]
    probe = Embedding.of([1, 0], "m")
    (score,) = scores_against([probe], enrolled, Aggregate.MAX)
    assert score == pytest.approx(1.0)
    (mean_score,) = scores_against([probe], enrolled, Aggregate.MEAN)
    assert mean_score < 1.0
    with pytest.raises(ModelMismatchError):
        scores_against([Embedding.of([1, 0], "other")], enrolled, Aggregate.MAX)
    assert np.isfinite(mean_score)
