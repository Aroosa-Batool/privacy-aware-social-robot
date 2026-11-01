from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

from pasr.domain.enums import ConsentSource, ReminderOrigin, ReminderStatus


@dataclass(frozen=True, slots=True, eq=False)
class Embedding:
    """A unit-length biometric embedding. ``model`` names the plugin model that produced it;
    embeddings from different models are never compared."""

    vector: npt.NDArray[np.float32]
    model: str

    @classmethod
    def of(cls, values: npt.ArrayLike, model: str) -> Embedding:
        vector = np.asarray(values, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            raise ValueError("cannot normalise a zero vector")
        return cls(vector=vector / norm, model=model)

    @property
    def dim(self) -> int:
        return int(self.vector.shape[0])


@dataclass(frozen=True, slots=True)
class Owner:
    display_name: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Bystander:
    id: str
    label: str
    first_seen_at: datetime
    last_seen_at: datetime
    seen_count: int


@dataclass(frozen=True, slots=True)
class Consent:
    id: int
    bystander_id: str
    allowed: bool
    reminder_id: int | None
    source: ConsentSource
    decided_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class Reminder:
    id: int
    title: str
    due_at: datetime
    sensitive: bool
    sensitivity_score: float | None
    sensitivity_source: str
    status: ReminderStatus
    origin: ReminderOrigin
    created_at: datetime
    delivered_at: datetime | None = None
