"""Owner registration: the robot learns the owner's face and voice as embeddings only.

The capture loops are module-level so threshold calibration can reuse them on other people's
samples without storing anything.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime, timedelta

from pasr.domain.enums import Biometric, Direction
from pasr.domain.models import Embedding, Owner
from pasr.hardware.protocols import Camera, Microphone
from pasr.live.feed import FaceMark, Tone
from pasr.orchestration.context import RobotContext
from pasr.orchestration.events import EventType
from pasr.perception.registry import PluginKind

VOICE_PROMPT = "Please talk to me for a few seconds so I can learn your voice."
FACE_GUIDANCE = "Look at the robot's camera, alone in the frame, until enough samples are in."
VOICE_GUIDANCE = "Speak naturally for about {seconds:.0f} seconds, for example about your day."


@dataclass(frozen=True, slots=True)
class EnrollProgress:
    modality: Biometric
    collected: int
    wanted: int
    frames: int = 0
    """Frames analysed (face) or speech segments heard (voice)."""
    no_face: int = 0
    many_faces: int = 0
    elapsed_s: float = 0.0


Progress = Callable[[EnrollProgress], None]
Describe = Callable[[Embedding, int], tuple[str, Tone]]
"""The live view's label for the n-th sample (calibration shows its similarity to the owner)."""


def counted(wanted: int) -> Describe:
    return lambda _probe, n: (f"Sample {n}/{wanted}", Tone.SAMPLE)


class EnrollmentError(RuntimeError):
    pass


async def capture_face_embeddings(
    ctx: RobotContext,
    *,
    wanted: int,
    deadline: datetime,
    camera: Camera | None = None,
    progress: Progress | None = None,
    describe: Describe | None = None,
) -> tuple[list[Embedding], EnrollProgress]:
    """Embeddings from frames that contain exactly one face, until ``wanted`` or ``deadline``."""
    describe = describe or counted(wanted)
    camera = camera or ctx.hardware.camera
    started = ctx.clock.now()
    samples: list[Embedding] = []
    frames = no_face = many_faces = 0

    def status() -> EnrollProgress:
        elapsed = (ctx.clock.now() - started).total_seconds()
        return EnrollProgress(
            Biometric.FACE, len(samples), wanted, frames, no_face, many_faces, elapsed
        )

    await ctx.hardware.head.look(Direction.FRONT)
    await camera.open()
    try:
        while len(samples) < wanted and ctx.clock.now() < deadline:
            frame = await camera.grab()
            faces = await ctx.compute(ctx.perception.face.detect_and_embed, frame)
            frames += 1
            if len(faces) == 1:
                samples.append(faces[0].embedding)
                marks = [FaceMark(faces[0].box, *describe(samples[-1], len(samples)))]
            elif not faces:
                no_face += 1
                marks = []
            else:  # several faces: we cannot tell which one is the owner
                many_faces += 1
                marks = [
                    FaceMark(face.box, "Several faces: not used", Tone.IGNORED) for face in faces
                ]
            ctx.live.face(frame, marks)
            if progress is not None:
                progress(status())
    finally:
        await camera.close()
    return samples, status()


async def capture_voice_embeddings(
    ctx: RobotContext,
    *,
    wanted: int,
    deadline: datetime,
    min_seconds: float,
    microphone: Microphone | None = None,
    progress: Progress | None = None,
    describe: Describe | None = None,
) -> tuple[list[Embedding], EnrollProgress]:
    """Embeddings of speech segments at least ``min_seconds`` long, until ``wanted`` or
    ``deadline``."""
    describe = describe or counted(wanted)
    started = ctx.clock.now()
    samples: list[Embedding] = []
    heard = 0

    def status() -> EnrollProgress:
        elapsed = (ctx.clock.now() - started).total_seconds()
        return EnrollProgress(Biometric.VOICE, len(samples), wanted, heard, elapsed_s=elapsed)

    async with aclosing(ctx.speech_segments(deadline, microphone=microphone)) as segments:
        async for segment in segments:
            heard += 1
            if segment.duration_s >= min_seconds:
                samples.append(await ctx.compute(ctx.perception.speaker.embed, segment))
                ctx.live.voice(segment.duration_s, *describe(samples[-1], len(samples)))
            else:
                ctx.live.voice(segment.duration_s, "Too short: not used", Tone.IGNORED)
            if progress is not None:
                progress(status())
            if len(samples) >= wanted:
                break
    return samples, status()


class EnrollmentService:
    def __init__(self, ctx: RobotContext) -> None:
        self.ctx = ctx

    def register(self, display_name: str) -> Owner:
        name = display_name.strip()
        if not name:
            raise EnrollmentError("the owner needs a name")
        return self.ctx.repos.owner.save(name, self.ctx.clock.now())

    def _require_owner(self) -> None:
        if self.ctx.repos.owner.get() is None:
            raise EnrollmentError("register the owner before enrolling face or voice")

    def _deadline(self) -> datetime:
        timeout = self.ctx.settings.identity.enroll_timeout_seconds
        return self.ctx.clock.now() + timedelta(seconds=timeout)

    async def enroll_face(self, progress: Progress | None = None) -> int:
        """Capture face embeddings from frames that contain exactly one face."""
        self._require_owner()
        wanted = self.ctx.settings.identity.enroll_face_samples
        with self.ctx.live.activity(
            "Enrolling the owner's face", "Only frames with exactly one face are used"
        ):
            samples, status = await capture_face_embeddings(
                self.ctx, wanted=wanted, deadline=self._deadline(), progress=progress
            )
        if len(samples) < wanted:
            if status.frames == 0:
                raise EnrollmentError("the camera produced no frames before the timeout")
            if status.no_face == status.frames:
                raise EnrollmentError(
                    f"saw no face in {status.frames} frames: check hardware.camera.name "
                    "(`pasr hardware list`), the lighting, and that the head faces you"
                )
            raise EnrollmentError(
                f"saw exactly one face in only {len(samples)} of {status.frames} frames "
                f"(none in {status.no_face}, several in {status.many_faces}); make sure only "
                "the owner is in front of the camera"
            )
        return self._store(Biometric.FACE, samples, PluginKind.FACE)

    async def enroll_voice(self, progress: Progress | None = None) -> int:
        """Capture voice embeddings from the owner's speech segments."""
        self._require_owner()
        identity = self.ctx.settings.identity
        wanted = identity.enroll_voice_samples
        await self.ctx.hardware.speaker.say(VOICE_PROMPT)
        with self.ctx.live.activity(
            "Enrolling the owner's voice",
            f"Speech segments of at least {identity.min_voice_segment_seconds:g} s are used",
        ):
            samples, status = await capture_voice_embeddings(
                self.ctx,
                wanted=wanted,
                deadline=self._deadline(),
                min_seconds=identity.min_voice_segment_seconds,
                progress=progress,
            )
        if len(samples) < wanted:
            raise EnrollmentError(
                f"heard only {len(samples)} of {wanted} usable speech segments "
                f"({status.frames} heard; shorter than {identity.min_voice_segment_seconds:g} s "
                "are ignored); speak for longer in a quiet room, or try perception.vad=silero"
            )
        return self._store(Biometric.VOICE, samples, PluginKind.SPEAKER)

    def _store(self, modality: Biometric, samples: list[Embedding], kind: PluginKind) -> int:
        count = self.ctx.repos.owner.replace_embeddings(modality, samples, self.ctx.clock.now())
        self.ctx.bus.emit(
            EventType.OWNER_ENROLLED,
            modality=modality.value,
            samples=count,
            plugin=self.ctx.perception.plugin_name(kind),
        )
        return count

    def delete(self, modality: Biometric) -> int:
        return self.ctx.repos.owner.delete_embeddings(modality)
