"""Owner registration: the robot learns the owner's face and voice as embeddings only.

The face is guided: the robot asks the owner to look straight at it, then to turn and tilt
their head each way, and keeps only frames that show them in full view looking the asked way,
so the stored samples cover the views the room scan will see. While a pose brings no image it
says what is wrong, it asks again at the end for each pose that fell short, and it always says
how enrolment went.

The voice is guided too (ADR 0013): the owner reads a text on the screen aloud, then talks
freely, until the robot has ``identity.enroll_voice_seconds`` of speech. It is stored as samples
of a few seconds each, and a sample unlike the others (a noise, someone else talking) is left
out.

The capture loops are module-level so threshold calibration can reuse them on other people's
samples without storing anything.
"""

from __future__ import annotations

import dataclasses
import math
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pasr.domain.enums import Biometric, Direction, FacePose
from pasr.domain.framing import FullView, PoseCheck, PoseMiss, ViewProblem, turned, view_problems
from pasr.domain.identity import leave_one_out
from pasr.domain.media import Frame, SpeechSegment
from pasr.domain.models import Embedding, Owner
from pasr.hardware.protocols import Camera, Microphone
from pasr.live.feed import FaceMark, Tone
from pasr.orchestration.context import RobotContext
from pasr.orchestration.events import EventType
from pasr.perception.protocols import FaceObservation
from pasr.perception.registry import PluginKind
from pasr.settings.schema import IdentitySettings

FACE_GUIDANCE = (
    "Sit alone in front of the robot, about an arm's length away, and do what it says: look "
    "straight at its camera, then turn and tilt your head each way. Hold each pose until it "
    "asks for the next."
)
VOICE_GUIDANCE = (
    "Be alone in a quiet room, where you usually sit near the robot, and speak at your normal "
    "loudness. When the robot asks, read the text below aloud until it stops you, then tell it "
    "about your day in your own words. It needs about {seconds:.0f} seconds of your speech."
)
VOICE_PASSAGE = (
    "A dispute arose between the North Wind and the Sun, each claiming that he was stronger "
    "than the other. At last they agreed to try their powers upon a traveller, to see which "
    "could soonest strip him of his cloak. The North Wind had the first try; and, gathering up "
    "all his force for the attack, he came whirling furiously down upon the man, and caught up "
    "his cloak as though he would wrest it from him by one single effort: but the harder he "
    "blew, the more closely the man wrapped it round himself. Then came the turn of the Sun. "
    "At first he beamed gently upon the traveller, who soon unclasped his cloak and walked on "
    "with it hanging loosely about his shoulders: then he shone forth in his full strength, "
    "and the man, before he had gone many steps, was glad to throw his cloak right off and "
    "complete his journey more lightly clad. Persuasion is better than force."
)
"""Read aloud while the robot learns the owner's voice: Aesop's fable *The North Wind and the
Sun* (V. S. Vernon Jones's translation, 1912, public domain), the text phoneticians use to show
the sounds of a language. It is longer than the reading takes, so the reader never runs out."""
VOICE_READ_PROMPT = (
    "Please read the text on the screen aloud, at your normal loudness, until I stop you."
)
VOICE_FREE_PROMPT = "Thank you. Now please tell me about your day, in your own words."
READ_SHARE = 2 / 3
"""Of the enrolment speech, and of its time, the share read aloud. The rest is in the owner's
own words, the kind of speech the robot hears while it listens: a voice enrolled in one
speaking style is harder to recognise in another."""
VOICE_CHUNK_SECONDS = 4.0
"""Speech per stored voice sample. Consecutive speech segments are joined to this length:
speaker models are trained on stretches of a few seconds and are unreliable on one."""
MIN_VOICE_SAMPLES = 3
"""Fewest voice samples, alike enough, that enrolment stores."""

POSE_REQUESTS = {
    FacePose.FRONT: "Please look straight at my camera.",
    FacePose.LEFT: "Please turn your head about halfway to your left.",
    FacePose.RIGHT: "Please turn your head about halfway to your right.",
    FacePose.UP: "Please tilt your chin up a little.",
    FacePose.DOWN: "Please tilt your chin down a little.",
}
TOWARDS = {
    FacePose.LEFT: "to your left",
    FacePose.RIGHT: "to your right",
    FacePose.UP: "up",
    FacePose.DOWN: "down",
}
POSE_LABELS = {
    FacePose.FRONT: "looking straight",
    FacePose.LEFT: "turned left",
    FacePose.RIGHT: "turned right",
    FacePose.UP: "chin up",
    FacePose.DOWN: "chin down",
}
"""What the live view says a face was not, when it did not point the asked way."""
POSE_MISSED = {
    FacePose.FRONT: "looking straight at me",
    FacePose.LEFT: "turned to your left",
    FacePose.RIGHT: "turned to your right",
    FacePose.UP: "with your chin up",
    FacePose.DOWN: "with your chin down",
}
NO_FRAMES = "no_frames"
NO_FACE = "no_face"
SEVERAL_FACES = "several_faces"
OUT_OF_TIME = "out_of_time"
FACE_HINTS: dict[str, str] = {
    NO_FRAMES: "My camera sends no pictures.",
    NO_FACE: "I cannot see your face. Please sit in front of me.",
    SEVERAL_FACES: "I can see more than one face. Please make sure you are alone.",
    ViewProblem.CUT_OFF: "Please sit right in front of me.",
    ViewProblem.SMALL: "Please come a little closer to me.",
    ViewProblem.UNCLEAR: "Please find better light, and keep still.",
}
"""What the robot says to put right the commonest reason frames were not used."""
TRY_AGAIN = "Let's try that one again."
FACE_LEARNED = "Thank you, I have learned your face."
FACE_PARTLY_LEARNED = (
    "Thank you, I have learned your face. But I could not see you {missed}; capture your face "
    "again to add that."
)
FACE_FAILED = "Sorry, I could not learn your face. {hint} Please try once more."
VOICE_LEARNED = "Thank you, I have learned your voice."
VOICE_FAILED = (
    "Sorry, I did not hear enough of your voice. Please speak a little longer, in a quiet room, "
    "and try once more."
)
VOICE_UNCLEAR = (
    "Sorry, your voice did not come through clearly. Please try once more, alone and in a "
    "quiet room."
)
POSES_DONE = "Thank you, you can relax now."
SETTLE_SECONDS = 1.0
"""Time to take a pose after the robot asks for it, before frames are used."""
SAMPLE_INTERVAL_S = 0.5
"""Least time between two images of one pose, so they are not copies of one moment."""
REMIND_SECONDS = 5.0
"""While a pose brings no new image for this long, the robot says what is wrong."""
SPEECH_ALLOWANCE_S = 10.0
"""Upper bound for what the robot says and waits per pose, besides the pose's own time."""


def face_enrolment_seconds(identity: IdentitySettings) -> float:
    """Longest a guided face capture takes once the camera is open, every pose asked for twice,
    for callers waiting on it."""
    poses = len(identity.enroll_face_poses)
    return 2 * poses * (identity.enroll_face_pose_seconds + SPEECH_ALLOWANCE_S)


def voice_enrolment_seconds(identity: IdentitySettings) -> float:
    """Longest a guided voice capture takes, with what the robot says, for callers waiting on
    it."""
    return identity.enroll_timeout_seconds + 3 * SPEECH_ALLOWANCE_S


def pose_hint(pose: FacePose, miss: PoseMiss) -> str:
    """What the robot says to a face that does not point the way ``pose`` asks."""
    if pose is FacePose.FRONT:
        return "Please look straight at my camera, and hold still."
    towards = TOWARDS[pose]
    if pose in (FacePose.LEFT, FacePose.RIGHT):
        hints = {
            PoseMiss.TOO_LITTLE: f"Please turn your head a bit further {towards}.",
            PoseMiss.TOO_FAR: f"Not quite so far, please: about halfway {towards}.",
            PoseMiss.WRONG_WAY: f"The other way, please: turn your head {towards}.",
        }
    else:
        hints = {
            PoseMiss.TOO_LITTLE: f"Please tilt your chin {towards} a bit more.",
            PoseMiss.WRONG_WAY: f"The other way, please: tilt your chin {towards}.",
            PoseMiss.TURNED: f"Please face me, and tilt your chin {towards}.",
        }
    return hints.get(miss, POSE_REQUESTS[pose])


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
    unusable: int = 0
    """Frames with one face that was not in full view or not looking the asked way."""
    pose: FacePose | None = None
    """The pose being captured (guided face capture)."""
    unit: str = "samples"
    """What ``collected`` and ``wanted`` count (voice enrolment: seconds of speech)."""


@dataclass(slots=True)
class PoseCapture:
    """What a face capture got for one pose (``None``: any pose), and why it did not use the
    other frames."""

    pose: FacePose | None
    samples: list[Embedding] = field(default_factory=list)
    frames: int = 0
    no_face: int = 0
    many_faces: int = 0
    unusable: int = 0
    misses: Counter[str] = field(default_factory=Counter)
    """Why lone faces were not used: ``ViewProblem`` and ``PoseMiss`` values."""
    turns: list[float] = field(default_factory=list)
    """``framing.turned`` of each lone face."""
    tilts: list[float] = field(default_factory=list)
    """``PoseCheck.tilted`` of each lone face seen after straight-ahead faces."""
    seconds: float = 0.0

    def cause(self) -> str:
        """The commonest reason frames were not used: ``NO_FACE``, ``SEVERAL_FACES``, or a
        ``ViewProblem`` or ``PoseMiss`` value; ``NO_FRAMES`` without frames, ``OUT_OF_TIME``
        if every frame was used."""
        if not self.frames:
            return NO_FRAMES
        counts = Counter({NO_FACE: self.no_face, SEVERAL_FACES: self.many_faces})
        counts.update(self.misses)
        counts = +counts  # drops the reasons that never happened
        return str(counts.most_common(1)[0][0]) if counts else OUT_OF_TIME

    def hint(self) -> str:
        """What the robot says to put the commonest problem right."""
        cause = self.cause()
        if cause in FACE_HINTS:
            return FACE_HINTS[cause]
        if self.pose is not None and cause in set(PoseMiss):
            return pose_hint(self.pose, PoseMiss(cause))
        return POSE_REQUESTS[self.pose] if self.pose else FACE_HINTS[NO_FACE]

    def measure(self, face: FaceObservation, check: PoseCheck) -> None:
        if face.landmarks is None or len(face.landmarks) < 3:
            return
        self.turns.append(turned(face.landmarks))
        moved = check.tilted(face.landmarks)
        if moved is not None:
            self.tilts.append(moved)


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
    poses: Sequence[FacePose] | None,
    per_pose: int,
    pose_seconds: float,
    camera: Camera | None = None,
    progress: Progress | None = None,
    describe: Describe | None = None,
) -> tuple[list[PoseCapture], EnrollProgress]:
    """Embeddings from frames with exactly one face, in full view, ``per_pose`` for each pose.
    The robot asks for the poses in turn, says what is wrong while a pose brings no image, and
    asks once more at the end for each pose that fell short; ``pose_seconds`` each time. The
    front pose is asked for again at once, and ends the capture if it falls short twice.
    ``poses`` ``None``: one step in any pose, without speech (image folders)."""
    captures = [PoseCapture(pose) for pose in ([None] if poses is None else poses)]
    wanted = per_pose * len(captures)
    describe = describe or counted(wanted)
    camera = camera or ctx.hardware.camera
    # how far a face may turn is the pose's to decide
    rules = dataclasses.replace(ctx.settings.scan.follow.full_view(), max_turned=math.inf)
    check = PoseCheck()
    started = ctx.clock.now()
    current = captures[0]

    def status() -> EnrollProgress:
        return EnrollProgress(
            Biometric.FACE,
            sum(len(c.samples) for c in captures),
            wanted,
            sum(c.frames for c in captures),
            sum(c.no_face for c in captures),
            sum(c.many_faces for c in captures),
            (ctx.clock.now() - started).total_seconds(),
            sum(c.unusable for c in captures),
            current.pose,
        )

    async def take(capture: PoseCapture) -> None:
        nonlocal current
        current, begun = capture, ctx.clock.now()
        pose, note = capture.pose, POSE_REQUESTS[capture.pose] if capture.pose else ""
        if note:
            await ctx.hardware.speaker.say(note)
            await ctx.clock.sleep(SETTLE_SECONDS)
        deadline = ctx.clock.now() + timedelta(seconds=pose_seconds)
        quiet_since = ctx.clock.now()
        while len(capture.samples) < per_pose and ctx.clock.now() < deadline:
            if note and ctx.clock.now() - quiet_since >= timedelta(seconds=REMIND_SECONDS):
                await ctx.hardware.speaker.say(capture.hint())
                quiet_since = ctx.clock.now()
            frame = await camera.grab()
            faces = await ctx.compute(ctx.perception.face.detect_and_embed, frame)
            capture.frames += 1
            taken = False
            if len(faces) == 1:
                face = faces[0]
                capture.measure(face, check)
                misses = _misses(face, frame, rules, check, pose)
                if misses:
                    capture.unusable += 1
                    capture.misses.update(misses)
                    marks = [FaceMark(face.box, _label(misses, pose), Tone.IGNORED)]
                else:
                    taken = True
                    capture.samples.append(face.embedding)
                    quiet_since = ctx.clock.now()
                    marks = [FaceMark(face.box, *describe(face.embedding, status().collected))]
            elif not faces:
                capture.no_face += 1
                marks = []
            else:  # several faces: we cannot tell which one is the owner
                capture.many_faces += 1
                marks = [
                    FaceMark(face.box, "Several faces: not used", Tone.IGNORED) for face in faces
                ]
            ctx.live.face(frame, marks, note=note)
            if progress is not None:
                progress(status())
            if taken and note and len(capture.samples) < per_pose:
                await ctx.clock.sleep(SAMPLE_INTERVAL_S)
        capture.seconds += (ctx.clock.now() - begun).total_seconds()

    def short(capture: PoseCapture) -> bool:
        return capture.pose is not None and len(capture.samples) < per_pose

    await ctx.hardware.head.look(Direction.FRONT)
    await camera.open()
    try:
        for capture in captures:
            await take(capture)
            if capture.pose is FacePose.FRONT and short(capture):  # at once: it is needed
                await ctx.hardware.speaker.say(TRY_AGAIN)
                await take(capture)
                if short(capture):  # nothing is stored without it, and up and down need it
                    return captures, status()
        for capture in captures:
            if short(capture):
                await ctx.hardware.speaker.say(TRY_AGAIN)
                await take(capture)
    finally:
        await camera.close()
    return captures, status()


def _misses(
    face: FaceObservation,
    frame: Frame,
    rules: FullView,
    check: PoseCheck,
    pose: FacePose | None,
) -> tuple[str, ...]:
    """Why a lone face is not used as a sample: ``ViewProblem`` values, or one ``PoseMiss``;
    empty if it is used."""
    if face.box is not None:
        height, width = frame.image.shape[:2]
        problems = view_problems(face.box, face.score, face.landmarks, (width, height), rules)
        if problems:
            return problems
    miss = check.miss(pose, face.landmarks) if pose is not None else None
    return (miss,) if miss else ()


def _label(misses: tuple[str, ...], pose: FacePose | None) -> str:
    if pose is not None and misses[0] in set(PoseMiss):
        return f"Not {POSE_LABELS[pose]} ({misses[0]}): not used"
    return f"Not in full view ({', '.join(misses)}): not used"


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


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


@dataclass(slots=True)
class VoiceCapture:
    """What a guided voice capture got: samples of about ``VOICE_CHUNK_SECONDS`` of speech."""

    samples: list[Embedding] = field(default_factory=list)
    seconds: float = 0.0
    """Speech in ``samples``."""
    heard: int = 0
    """Speech segments heard, short ones included."""


async def capture_voice_samples(
    ctx: RobotContext,
    *,
    seconds: float,
    timeout_s: float,
    min_seconds: float,
    progress: Progress | None = None,
) -> VoiceCapture:
    """The owner's voice: the robot asks them to read ``VOICE_PASSAGE`` aloud for
    ``READ_SHARE`` of ``seconds`` of speech, then to talk freely for the rest, with the same
    shares of ``timeout_s`` (the microphone is closed while the robot speaks). Speech segments of
    at least ``min_seconds`` are joined into samples of about ``VOICE_CHUNK_SECONDS``; the last,
    shorter one is kept if it holds half of that."""
    capture = VoiceCapture()
    started = ctx.clock.now()
    goal = 0.0

    def status(buffered: float) -> EnrollProgress:
        return EnrollProgress(
            Biometric.VOICE,
            int(capture.seconds + buffered),
            round(seconds),
            capture.heard,
            elapsed_s=(ctx.clock.now() - started).total_seconds(),
            unit="s of speech",
        )

    async def add(buffer: list[SpeechSegment]) -> None:
        joined = SpeechSegment.joined(buffer)
        capture.samples.append(await ctx.compute(ctx.perception.speaker.embed, joined))
        capture.seconds += sum(s.duration_s for s in buffer)

    for prompt, share in ((VOICE_READ_PROMPT, READ_SHARE), (VOICE_FREE_PROMPT, 1 - READ_SHARE)):
        goal += share * seconds
        await ctx.hardware.speaker.say(prompt)
        deadline = ctx.clock.now() + timedelta(seconds=share * timeout_s)
        buffer: list[SpeechSegment] = []
        async with aclosing(ctx.speech_segments(deadline)) as segments:
            async for segment in segments:
                capture.heard += 1
                if segment.duration_s < min_seconds:
                    ctx.live.voice(segment.duration_s, "Too short: not used", Tone.IGNORED)
                else:
                    buffer.append(segment)
                    if sum(s.duration_s for s in buffer) >= VOICE_CHUNK_SECONDS:
                        await add(buffer)
                        buffer = []
                    used = capture.seconds + sum(s.duration_s for s in buffer)
                    label = f"Speech {used:.0f}/{seconds:.0f} s"
                    ctx.live.voice(segment.duration_s, label, Tone.SAMPLE)
                if progress is not None:
                    progress(status(sum(s.duration_s for s in buffer)))
                if capture.seconds >= goal:
                    break
        if sum(s.duration_s for s in buffer) >= VOICE_CHUNK_SECONDS / 2:
            await add(buffer)
    return capture


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

    async def enroll_face(self, progress: Progress | None = None) -> int:
        """Capture face embeddings of each pose the robot asks for, from frames with exactly
        one face in full view, looking the asked way. They are stored once the straight-ahead
        pose came out; a pose that did not is left out. The robot says how it went."""
        self._require_owner()
        identity = self.ctx.settings.identity
        per_pose = identity.enroll_face_samples
        with self.ctx.live.activity(
            "Enrolling the owner's face",
        ):
            captures, status = await capture_face_embeddings(
                self.ctx,
                poses=identity.enroll_face_poses,
                per_pose=per_pose,
                pose_seconds=identity.enroll_face_pose_seconds,
                progress=progress,
            )
        for capture in captures:
            self._log_pose(capture)
        front = next(c for c in captures if c.pose is FacePose.FRONT)
        if len(front.samples) < per_pose:
            self.ctx.bus.emit(
                EventType.OWNER_ENROLMENT_FAILED,
                modality=Biometric.FACE.value,
                pose=FacePose.FRONT.value,
                reason=front.cause(),
            )
            await self.ctx.hardware.speaker.say(FACE_FAILED.format(hint=front.hint()))
            raise EnrollmentError(_face_failure(front, status, per_pose))
        samples = [sample for capture in captures for sample in capture.samples]
        count = self._store(Biometric.FACE, samples, PluginKind.FACE)
        missed = [c.pose for c in captures if c.pose and len(c.samples) < per_pose]
        if missed:
            text = " or ".join(POSE_MISSED[pose] for pose in missed)
            await self.ctx.hardware.speaker.say(FACE_PARTLY_LEARNED.format(missed=text))
        else:
            await self.ctx.hardware.speaker.say(FACE_LEARNED)
        return count

    def _log_pose(self, capture: PoseCapture) -> None:
        """One ``owner.face_pose`` event per pose: what it got and why frames went unused."""
        unused = not capture.frames or len(capture.samples) < capture.frames
        self.ctx.bus.emit(
            EventType.FACE_POSE_CAPTURED,
            pose=capture.pose.value if capture.pose else None,
            samples=len(capture.samples),
            frames=capture.frames,
            no_face=capture.no_face,
            several=capture.many_faces,
            unusable=capture.unusable,
            reason=capture.cause() if unused else None,
            turned=_median(capture.turns),
            tilt=_median(capture.tilts),
            seconds=round(capture.seconds, 1),
        )

    async def enroll_voice(self, progress: Progress | None = None) -> int:
        """Capture the owner's voice, read aloud and then in their own words, as samples of a
        few seconds each. They are stored once ``identity.enroll_voice_seconds`` of speech came
        in, without samples unlike the others (``leave_one_out`` below the voice threshold), if
        at least ``MIN_VOICE_SAMPLES`` remain. The robot says how it went."""
        self._require_owner()
        identity = self.ctx.settings.identity
        wanted = identity.enroll_voice_seconds
        with self.ctx.live.activity(
            "Enrolling the owner's voice",
            f"Speech segments of at least {identity.min_voice_segment_seconds:g} s are joined "
            f"into samples of about {VOICE_CHUNK_SECONDS:g} s",
        ):
            capture = await capture_voice_samples(
                self.ctx,
                seconds=wanted,
                timeout_s=identity.enroll_timeout_seconds,
                min_seconds=identity.min_voice_segment_seconds,
                progress=progress,
            )
        fits = leave_one_out(capture.samples)  # none for a lone sample: it is not kept
        kept = [
            s
            for s, fit in zip(capture.samples, fits, strict=False)
            if fit >= identity.voice_threshold
        ]
        heard = round(capture.seconds, 1)
        if capture.seconds < wanted or len(kept) < MIN_VOICE_SAMPLES:
            enough = capture.seconds >= wanted
            self.ctx.bus.emit(
                EventType.OWNER_ENROLMENT_FAILED,
                modality=Biometric.VOICE.value,
                reason="unlike samples" if enough else "too little speech",
                samples=len(kept),
                seconds=heard,
            )
            await self.ctx.hardware.speaker.say(VOICE_UNCLEAR if enough else VOICE_FAILED)
            raise EnrollmentError(
                f"only {len(kept)} of {len(capture.samples)} voice samples sound alike (each "
                f"against the others, at identity.voice_threshold {identity.voice_threshold:g}): "
                "someone else may have spoken, or a noise was loud; try again alone in a quiet "
                "room"
                if enough
                else f"heard {capture.seconds:.0f} of {wanted:.0f} s of usable speech in "
                f"{capture.heard} speech segments (shorter than "
                f"{identity.min_voice_segment_seconds:g} s are ignored); read the text aloud at "
                "your normal loudness in a quiet room, or try perception.vad=silero"
            )
        count = self._store(
            Biometric.VOICE,
            kept,
            PluginKind.SPEAKER,
            seconds=heard,
            unusable=len(capture.samples) - len(kept),
            similarity=_median([f for f in fits if f >= identity.voice_threshold]),
        )
        await self.ctx.hardware.speaker.say(VOICE_LEARNED)
        return count

    def _store(
        self,
        modality: Biometric,
        samples: list[Embedding],
        kind: PluginKind,
        *,
        seconds: float | None = None,
        unusable: int | None = None,
        similarity: float | None = None,
    ) -> int:
        """Replace the owner's samples; the voice's event gives the seconds of speech, the
        samples left out and how alike the stored ones are."""
        count = self.ctx.repos.owner.replace_embeddings(modality, samples, self.ctx.clock.now())
        self.ctx.bus.emit(
            EventType.OWNER_ENROLLED,
            modality=modality.value,
            samples=count,
            plugin=self.ctx.perception.plugin_name(kind),
            seconds=seconds,
            unusable=unusable,
            similarity=similarity,
        )
        return count

    def delete(self, modality: Biometric) -> int:
        return self.ctx.repos.owner.delete_embeddings(modality)


def _face_failure(front: PoseCapture, status: EnrollProgress, per_pose: int) -> str:
    if status.frames == 0:
        return "the camera produced no frames before the timeout"
    if status.no_face == status.frames:
        return (
            f"saw no face in {status.frames} frames: check hardware.camera.name "
            "(`pasr hardware list`), the lighting, and that the head faces you"
        )
    return (
        f"too few images of you looking straight at the camera ({len(front.samples)}/"
        f"{per_pose} in {front.frames} frames: no face in {front.no_face}, several faces in "
        f"{front.many_faces}, not usable in {front.unusable}, mostly '{front.cause()}'). "
        f"{front.hint()} Nothing was stored."
    )
