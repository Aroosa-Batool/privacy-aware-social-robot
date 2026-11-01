"""InsightFace ``buffalo_l``: SCRFD detector + ArcFace recognition on onnxruntime (CPU).

Only the detection and recognition models are loaded , never the age/gender model. Weights
are downloaded once into ``<models_dir>/insightface/models/buffalo_l`` and are licensed for
non-commercial research only (docs/PRIVACY.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from pasr.domain.media import Frame
from pasr.domain.models import Embedding
from pasr.paths import resolve
from pasr.perception.lazy import LazyEngine
from pasr.perception.protocols import FaceObservation
from pasr.settings.tiers import setting

MODEL_PACK = "buffalo_l"


class InsightFaceEmbedder(LazyEngine):
    recommended_threshold: ClassVar[float | None] = 0.40
    """Cosine similarity starting point for ArcFace embeddings; calibrate with `pasr calibrate`."""

    class Params(BaseModel):
        models_dir: Path = setting(
            Path("models"),
            tier="advanced",
            description="Where the model pack is downloaded (storage.models_dir by default).",
        )
        det_size: int = setting(
            640,
            tier="advanced",
            ge=160,
            le=1280,
            multiple_of=32,
            description="Detector input size: smaller is faster, larger finds small faces.",
        )
        min_det_score: float = setting(
            0.5, tier="advanced", ge=0, le=1, description="Ignore detections below this score."
        )

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params
        self.model = f"insightface-{MODEL_PACK}"

    def detect_and_embed(self, frame: Frame) -> list[FaceObservation]:
        app = self._engine_or_load()
        with self._lock:
            faces = app.get(frame.image)
        return [
            FaceObservation(
                Embedding.of(face.normed_embedding, self.model),
                float(face.det_score),
                box=_box(face.bbox),
                landmarks=_points(face.kps),
            )
            for face in faces
            if float(face.det_score) >= self.params.min_det_score
            and face.normed_embedding is not None
        ]

    # --- the only code that talks to insightface -----------------------------------------

    def _load(self) -> Any:
        import onnxruntime  # noqa: F401 - fail here, with the extra hint, if it is missing
        from insightface.app import FaceAnalysis

        root = resolve(self.params.models_dir) / "insightface"
        root.mkdir(parents=True, exist_ok=True)
        app = FaceAnalysis(
            name=MODEL_PACK,
            root=str(root),
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        size = self.params.det_size
        app.prepare(ctx_id=0, det_thresh=self.params.min_det_score, det_size=(size, size))
        return app


def _box(bbox: Any) -> tuple[float, float, float, float] | None:
    if bbox is None or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = (float(v) for v in bbox)
    return x1, y1, x2, y2


def _points(kps: Any) -> tuple[tuple[float, float], ...] | None:
    """SCRFD's five landmarks: both eyes, the nose tip and both mouth corners."""
    if kps is None or len(kps) < 3:
        return None
    return tuple((float(x), float(y)) for x, y in kps)
