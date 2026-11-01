import numpy as np
import pytest

from pasr.domain.enums import Biometric
from pasr.domain.identity import (
    Aggregate,
    IdentityKind,
    ModelMismatchError,
    NotEnrolledError,
    cosine,
    identify,
    similarity,
)
from pasr.domain.models import Embedding


def emb(*values: float, model: str = "m") -> Embedding:
    return Embedding.of(values, model)


OWNER = [emb(1, 0, 0), emb(0.9, 0.1, 0)]


def run(probe, bystanders=None, threshold=0.8, aggregate=Aggregate.MAX):
    return identify(
        probe,
        modality=Biometric.VOICE,
        owner=OWNER,
        bystanders=bystanders or {},
        threshold=threshold,
        aggregate=aggregate,
    )


def test_embeddings_are_unit_length():
    assert np.isclose(np.linalg.norm(emb(3, 4).vector), 1.0)
    assert cosine(emb(1, 0), emb(0, 1)) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        emb(0, 0)


def test_owner_is_recognised():
    result = run(emb(1, 0.05, 0))
    assert result.kind is IdentityKind.OWNER
    assert result.owner_similarity > 0.99


def test_stranger_is_new_and_known_bystander_matches():
    assert run(emb(0, 0, 1)).kind is IdentityKind.NEW_BYSTANDER
    result = run(emb(0, 0.1, 1), bystanders={"b1": [emb(0, 0, 1)], "b2": [emb(0, 1, 0)]})
    assert result.kind is IdentityKind.KNOWN_BYSTANDER
    assert result.bystander_id == "b1"


def test_threshold_boundary_is_inclusive():
    probe = emb(1, 1, 0)
    exact = similarity(probe, OWNER, Aggregate.MAX)
    assert run(probe, threshold=exact).kind is IdentityKind.OWNER
    assert run(probe, threshold=exact + 1e-4).kind is IdentityKind.NEW_BYSTANDER


def test_mean_aggregate_uses_the_averaged_reference():
    references = [emb(1, 0), emb(0, 1)]
    probe = emb(1, 1)
    assert similarity(probe, references, Aggregate.MAX) == pytest.approx(0.7071, abs=1e-3)
    assert similarity(probe, references, Aggregate.MEAN) == pytest.approx(1.0)


def test_cross_model_comparison_is_refused():
    with pytest.raises(ModelMismatchError):
        run(emb(1, 0, 0, model="other"))


def test_bystanders_from_another_model_are_ignored():
    result = run(emb(0, 0, 1), bystanders={"old": [emb(0, 0, 1, model="other")]})
    assert result.kind is IdentityKind.NEW_BYSTANDER


def test_missing_enrolment_fails():
    with pytest.raises(NotEnrolledError):
        identify(
            emb(1, 0),
            modality=Biometric.FACE,
            owner=[],
            bystanders={},
            threshold=0.5,
            aggregate=Aggregate.MAX,
        )
