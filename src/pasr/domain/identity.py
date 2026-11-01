"""Identity matching on embeddings: is this face/voice the owner, a known bystander, or new?"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from pasr.domain.enums import Biometric
from pasr.domain.models import Embedding


class Aggregate(StrEnum):
    """How a probe is compared with several enrolled samples of one person."""

    MAX = "max"
    MEAN = "mean"


class IdentityKind(StrEnum):
    OWNER = "owner"
    KNOWN_BYSTANDER = "known_bystander"
    NEW_BYSTANDER = "new_bystander"


class IdentityError(Exception):
    """Identification is impossible; callers must fail closed (never disclose)."""


class NotEnrolledError(IdentityError):
    def __init__(self, modality: Biometric) -> None:
        super().__init__(f"the owner's {modality} is not enrolled")
        self.modality = modality


class ModelMismatchError(IdentityError):
    def __init__(self, probe_model: str, enrolled_models: set[str]) -> None:
        super().__init__(
            f"probe embedding comes from model {probe_model!r} but the owner was enrolled with "
            f"{sorted(enrolled_models)}; re-enrol the owner after changing perception plugins"
        )


@dataclass(frozen=True, slots=True)
class Identification:
    kind: IdentityKind
    owner_similarity: float
    bystander_id: str | None = None


def cosine(a: Embedding, b: Embedding) -> float:
    return float(np.dot(a.vector, b.vector))


def similarity(
    probe: Embedding, references: Sequence[Embedding], aggregate: Aggregate
) -> float | None:
    """Similarity of ``probe`` to one person's references, or ``None`` if no reference was
    produced by the same model."""
    same_model = [r for r in references if r.model == probe.model]
    if not same_model:
        return None
    if aggregate is Aggregate.MAX:
        return max(cosine(probe, r) for r in same_model)
    mean = Embedding.of(np.mean([r.vector for r in same_model], axis=0), probe.model)
    return cosine(probe, mean)


def identify(
    probe: Embedding,
    *,
    modality: Biometric,
    owner: Sequence[Embedding],
    bystanders: Mapping[str, Sequence[Embedding]],
    threshold: float,
    aggregate: Aggregate,
) -> Identification:
    if not owner:
        raise NotEnrolledError(modality)
    owner_similarity = similarity(probe, owner, aggregate)
    if owner_similarity is None:
        raise ModelMismatchError(probe.model, {e.model for e in owner})
    if owner_similarity >= threshold:
        return Identification(IdentityKind.OWNER, owner_similarity)

    best_id: str | None = None
    best = -1.0
    for bystander_id, references in bystanders.items():
        score = similarity(probe, references, aggregate)
        if score is not None and score > best:
            best_id, best = bystander_id, score
    if best_id is not None and best >= threshold:
        return Identification(IdentityKind.KNOWN_BYSTANDER, owner_similarity, best_id)
    return Identification(IdentityKind.NEW_BYSTANDER, owner_similarity)
