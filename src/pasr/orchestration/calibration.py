"""Measure how well the owner's enrolled embeddings separate the owner from other people, and
apply a threshold. Captured embeddings are scored and dropped; only the chosen threshold is
stored."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import timedelta

from pasr.domain.calibration import Calibration, scores_against
from pasr.domain.enums import Biometric
from pasr.domain.identity import ModelMismatchError, similarity
from pasr.domain.models import Embedding
from pasr.hardware.protocols import Camera, Microphone
from pasr.live.feed import Tone
from pasr.orchestration.context import RobotContext
from pasr.orchestration.enrollment import (
    POSES_DONE,
    Describe,
    EnrollmentError,
    Progress,
    capture_face_embeddings,
    capture_voice_embeddings,
)
from pasr.orchestration.events import EventType
from pasr.paths import resolve
from pasr.perception.registry import PluginKind
from pasr.settings.loader import update_overrides

THRESHOLD_FIELDS = {Biometric.FACE: "face_threshold", Biometric.VOICE: "voice_threshold"}
PLUGIN_KINDS = {Biometric.FACE: PluginKind.FACE, Biometric.VOICE: PluginKind.SPEAKER}


class CalibrationService:
    def __init__(self, ctx: RobotContext) -> None:
        self.ctx = ctx

    async def score_face(
        self,
        *,
        samples: int,
        timeout_s: float,
        guided: bool = True,
        camera: Camera | None = None,
        progress: Progress | None = None,
    ) -> list[float]:
        """Similarity of fresh single-face frames to the enrolled face, as the flow computes it:
        ``samples`` for each enrolment pose, which the robot asks for in turn (``timeout_s``
        each), or ``samples`` in any pose without ``guided`` (image folders)."""
        enrolled = self._enrolled(Biometric.FACE)
        poses = self.ctx.settings.identity.enroll_face_poses if guided else None
        wanted = samples * (len(poses) if poses else 1)
        with self._live(Biometric.FACE):
            captures, status = await capture_face_embeddings(
                self.ctx,
                poses=poses,
                per_pose=samples,
                pose_seconds=timeout_s,
                camera=camera,
                progress=progress,
                describe=self._describe(Biometric.FACE, enrolled, wanted),
            )
        if poses:
            await self.ctx.hardware.speaker.say(POSES_DONE)
        probes = [probe for capture in captures for probe in capture.samples]
        if not probes:
            raise EnrollmentError(
                f"no usable frame in {status.frames} frames (no face in {status.no_face}, "
                f"several in {status.many_faces}, not in full view or not looking the asked "
                f"way in {status.unusable})"
            )
        return self._score(probes, enrolled)

    async def score_voice(
        self,
        *,
        samples: int,
        timeout_s: float,
        microphone: Microphone | None = None,
        progress: Progress | None = None,
    ) -> list[float]:
        """Similarity of fresh speech segments to the enrolled voice, as the flow computes it."""
        enrolled = self._enrolled(Biometric.VOICE)
        with self._live(Biometric.VOICE):
            probes, status = await capture_voice_embeddings(
                self.ctx,
                wanted=samples,
                deadline=self._deadline(timeout_s),
                min_seconds=self.ctx.settings.identity.min_voice_segment_seconds,
                microphone=microphone,
                progress=progress,
                describe=self._describe(Biometric.VOICE, enrolled, samples),
            )
        if not probes:
            raise EnrollmentError(f"no usable speech segment ({status.frames} heard)")
        return self._score(probes, enrolled)

    def apply(
        self, modality: Biometric, threshold: float, calibration: Calibration | None = None
    ) -> None:
        """Store the threshold in the settings overrides and log that it was calibrated."""
        value = round(float(threshold), 3)
        field = THRESHOLD_FIELDS[modality]
        update_overrides(resolve(self.ctx.settings.storage.data_dir), {"identity": {field: value}})
        self.ctx.bus.emit(
            EventType.THRESHOLD_CALIBRATED,
            modality=modality.value,
            plugin=self.ctx.perception.plugin_name(PLUGIN_KINDS[modality]),
            threshold=value,
            count=calibration.genuine.count if calibration else 0,
        )

    def _threshold(self, modality: Biometric) -> float:
        threshold: float = getattr(self.ctx.settings.identity, THRESHOLD_FIELDS[modality])
        return threshold

    def _live(self, modality: Biometric) -> AbstractContextManager[None]:
        return self.ctx.live.activity(f"Calibrating the {modality.value} threshold")

    def _describe(self, modality: Biometric, enrolled: list[Embedding], wanted: int) -> Describe:
        threshold = self._threshold(modality)
        aggregate = self.ctx.settings.identity.aggregate

        def describe(probe: Embedding, n: int) -> tuple[str, Tone]:
            score = similarity(probe, enrolled, aggregate)
            if score is None:  # another model: scoring fails right after, with the reason
                return f"Sample {n}/{wanted}", Tone.IGNORED
            tone = Tone.OWNER if score >= threshold else Tone.OTHER
            return f"Sample {n}/{wanted}: {score:.2f}", tone

        return describe

    def _enrolled(self, modality: Biometric) -> list[Embedding]:
        enrolled = self.ctx.repos.owner.embeddings(modality)
        if not enrolled:
            raise EnrollmentError(f"enrol the owner's {modality.value} first")
        return enrolled

    def _deadline(self, timeout_s: float):  # type: ignore[no-untyped-def]
        return self.ctx.clock.now() + timedelta(seconds=timeout_s)

    def _score(self, probes: list[Embedding], enrolled: list[Embedding]) -> list[float]:
        try:
            return scores_against(probes, enrolled, self.ctx.settings.identity.aggregate)
        except ModelMismatchError as exc:
            raise EnrollmentError(f"re-enrol the owner with the current plugin: {exc}") from exc
