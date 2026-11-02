"""What happens when a reminder is due: check that the owner is present, detect bystanders, ask
for consent, deliver.

States and allowed transitions are listed in ``TRANSITIONS`` (diagram in docs/ARCHITECTURE.md).
The owner's watch must answer before the microphone or camera is used or anything is said out
loud (ADR 0007). Any error fails closed: the reminder goes to the watch, never out loud.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, aclosing
from dataclasses import dataclass, field, replace
from datetime import timedelta
from enum import StrEnum

from pasr.domain.enums import (
    Biometric,
    ConsentSource,
    DeliveryChannel,
    Direction,
    DisclosurePolicy,
    Pose,
    ReminderStatus,
    Tilt,
    WatchAnswer,
)
from pasr.domain.framing import ViewProblem, after_move, head_move, offset, view_problems
from pasr.domain.identity import Identification, IdentityKind, average, cosine, identify
from pasr.domain.media import Frame
from pasr.domain.models import Embedding, Reminder
from pasr.domain.policy import Decision, decide, requires_detection
from pasr.domain.timing import LATE_LISTEN_SHARE, listen_deadline, started_late
from pasr.live.feed import FaceMark, Tone
from pasr.orchestration.context import RobotContext
from pasr.orchestration.events import EventType
from pasr.orchestration.fsm import StateMachine, Transition
from pasr.orchestration.notices import describe
from pasr.perception.protocols import FaceObservation
from pasr.perception.registry import PluginKind

logger = logging.getLogger(__name__)


class DueState(StrEnum):
    IDLE = "IDLE"
    WAKING = "WAKING"
    CHECKING_PRESENCE = "CHECKING_PRESENCE"
    OWNER_AWAY = "OWNER_AWAY"
    LISTENING = "LISTENING"
    AUDIO_BYSTANDER = "AUDIO_BYSTANDER"
    SCANNING = "SCANNING"
    VISUAL_BYSTANDER = "VISUAL_BYSTANDER"
    NO_BYSTANDER = "NO_BYSTANDER"
    CHECK_MEMORY = "CHECK_MEMORY"
    AWAITING_CONSENT = "AWAITING_CONSENT"
    WAIT_FOR_DUE = "WAIT_FOR_DUE"
    DISCLOSE_SPEAK = "DISCLOSE_SPEAK"
    DISCLOSE_WATCH = "DISCLOSE_WATCH"
    DONE = "DONE"
    FAILED = "FAILED"


S = DueState
TRANSITIONS: dict[DueState, frozenset[DueState]] = {
    S.IDLE: frozenset({S.WAKING}),
    S.WAKING: frozenset({S.CHECKING_PRESENCE}),
    S.CHECKING_PRESENCE: frozenset(
        {S.OWNER_AWAY, S.LISTENING, S.SCANNING, S.AWAITING_CONSENT, S.WAIT_FOR_DUE}
    ),
    S.OWNER_AWAY: frozenset({S.WAIT_FOR_DUE}),
    S.LISTENING: frozenset({S.AUDIO_BYSTANDER, S.SCANNING, S.NO_BYSTANDER}),
    S.SCANNING: frozenset({S.VISUAL_BYSTANDER, S.NO_BYSTANDER, S.CHECK_MEMORY}),
    S.AUDIO_BYSTANDER: frozenset({S.CHECK_MEMORY, S.SCANNING}),
    S.VISUAL_BYSTANDER: frozenset({S.CHECK_MEMORY}),
    S.NO_BYSTANDER: frozenset({S.WAIT_FOR_DUE}),
    S.CHECK_MEMORY: frozenset({S.AWAITING_CONSENT, S.WAIT_FOR_DUE}),
    S.AWAITING_CONSENT: frozenset({S.WAIT_FOR_DUE}),
    S.WAIT_FOR_DUE: frozenset({S.DISCLOSE_SPEAK, S.DISCLOSE_WATCH}),
    S.DISCLOSE_SPEAK: frozenset({S.DONE}),
    S.DISCLOSE_WATCH: frozenset({S.DONE}),
    S.DONE: frozenset(),
    S.FAILED: frozenset(),
}


@dataclass(slots=True)
class DetectedPerson:
    """Someone other than the owner. ``key`` is a stored bystander id, or ``new-N`` until the
    bystander is remembered (only with the ask-once policy)."""

    key: str
    source: Biometric
    stored: bool
    embeddings: list[Embedding] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FlowOutcome:
    reminder_id: int
    states: tuple[DueState, ...]
    channel: DeliveryChannel | None
    bystanders: int
    error: str | None = None


MAX_STORED_EMBEDDINGS = 5

SAME_FACE = 0.3
"""Cosine similarity at or above which a face in the next frame is the one being followed.
Consecutive frames of one person score far above it, different people far below."""
NEAR = 0.5
"""Otherwise, a face this close (in half-image units) to where the followed face should be
after the head's move is taken to be it."""
MAX_MISSES = 2
"""Frames in a row without the followed face before the head gives up on it."""


class DueFlow:
    def __init__(self, ctx: RobotContext, reminder: Reminder) -> None:
        self.ctx = ctx
        self.reminder = reminder
        self.settings = ctx.settings  # one consistent snapshot for the whole flow
        self.fsm: StateMachine[DueState] = StateMachine(
            DueState.IDLE,
            TRANSITIONS,
            clock=ctx.clock,
            failure_state=DueState.FAILED,
            on_transition=self._on_transition,
        )
        self.detected: dict[str, DetectedPerson] = {}
        self.channel: DeliveryChannel | None = None
        self.planned: DeliveryChannel | None = None
        """The channel chosen before the due time; ``channel`` turns to the watch if the owner
        has left by then."""
        self.answer: WatchAnswer | None = None
        """The owner's answer on the watch, once asked for consent."""
        self.delivered: DeliveryChannel | None = None
        """Where the reminder went, once it got there."""
        self.problem: str | None = None
        """What went wrong, in words, for the dashboard. Kept in memory only: the event log
        records just the error's type."""
        self._new_ids = itertools.count(1)
        self._error: str | None = None

    @property
    def state(self) -> DueState:
        return self.fsm.state

    def _on_transition(self, t: Transition[DueState]) -> None:
        logger.info("reminder %s: %s → %s (%s)", self.reminder.id, t.source, t.target, t.reason)
        self.ctx.bus.emit(
            EventType.FLOW_STATE,
            reminder_id=self.reminder.id,
            state_from=t.source.value,
            state_to=t.target.value,
            reason=t.reason,
        )

    def _go(self, target: DueState, reason: str) -> None:
        self.fsm.go(target, reason)

    async def run(self) -> FlowOutcome:
        try:
            await self._run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(  # the dashboard shows the failed pipeline as a toast of its own
                "reminder %s failed; delivering to the watch",
                self.reminder.id,
                extra={"toast": False},
            )
            self._error = type(exc).__name__
            self.problem = describe(exc)
            self.ctx.bus.emit(
                EventType.FLOW_ERROR, reminder_id=self.reminder.id, error_type=self._error
            )
            self._go(DueState.FAILED, f"error: {self._error}")
            await self._fail_closed()
        return FlowOutcome(
            reminder_id=self.reminder.id,
            states=tuple(self.fsm.path()),
            channel=self.channel,
            bystanders=len(self.detected),
            error=self._error,
        )

    async def _run(self) -> None:
        privacy = self.settings.privacy
        reminder = self.reminder
        woke = self.ctx.clock.now()
        self._go(DueState.WAKING, "time to prepare the reminder")
        await self.ctx.hardware.head.pose(Pose.ATTENTION)

        self._go(DueState.CHECKING_PRESENCE, "asking the owner's watch before using any sensor")
        if not await self._owner_present():
            self._go(DueState.OWNER_AWAY, "the owner's watch did not answer")
            await self._deliver(DeliveryChannel.WATCH, "owner away: no listening, no camera")
            return

        if not requires_detection(
            policy=privacy.disclosure_policy,
            modality=privacy.detection_modality,
            sensitive=reminder.sensitive,
        ):
            decision = self._decide()
            if decision is Decision.SPEAK:
                reason = "not sensitive" if not reminder.sensitive else "policy: always disclose"
                await self._deliver(DeliveryChannel.SPOKEN, reason)
            else:
                self._go(DueState.AWAITING_CONSENT, "no sensors allowed: cannot tell who is here")
                await self._ask_consent()
            return

        modality = privacy.detection_modality
        heard_owner = False
        if modality.listens:
            lead = timedelta(minutes=self.settings.reminder.wake_lead_minutes)
            if modality.looks and started_late(woke, reminder.due_at, wake_lead=lead):
                self._go(
                    DueState.LISTENING,
                    f"started late: listening for {LATE_LISTEN_SHARE:.0%} of the time left, "
                    "then looking",
                )
                heard_owner = await self._listen(LATE_LISTEN_SHARE)
            else:
                self._go(DueState.LISTENING, "sensitive reminder: listening for other voices")
                heard_owner = await self._listen()
        # voices of people the owner allowed before do not end the search: the robot goes on
        # to look for anyone else, as if it had heard only the owner
        heard_allowed = bool(self.detected) and self._only_allowed()
        if self.detected and not heard_allowed:
            self._go(DueState.AUDIO_BYSTANDER, "heard someone other than the owner")
        elif modality.looks and (
            not modality.listens
            or not (heard_owner or heard_allowed)
            or self.settings.reminder.scan_if_only_owner_heard
        ):
            if heard_allowed:
                self._go(DueState.AUDIO_BYSTANDER, "heard only people the owner allowed before")
            self._go(
                DueState.SCANNING,
                "sensitive reminder: looking for bystanders, camera only"
                if not modality.listens
                else "only people allowed before heard: looking for silent bystanders"
                if heard_allowed
                else "only the owner heard: looking for silent bystanders"
                if heard_owner
                else "silence: looking for silent bystanders",
            )
            heard = set(self.detected)
            sweeps = await self._scan()
            if not self.detected:
                swept = f"{sweeps} full sweep(s)" if sweeps else "part of a sweep"
                self._go(DueState.NO_BYSTANDER, f"found no one: {swept} until the due time")
                await self._deliver(DeliveryChannel.SPOKEN, "owner is alone")
                return
            if set(self.detected) != heard:  # it saw someone; else straight to the decision
                self._go(
                    DueState.VISUAL_BYSTANDER,
                    "saw only people the owner allowed before, until the due time"
                    if self._only_allowed()
                    else "saw someone other than the owner",
                )
        elif heard_allowed:
            self._go(DueState.AUDIO_BYSTANDER, "heard only people the owner allowed before")
        else:
            self._go(DueState.NO_BYSTANDER, "no other voices heard")
            await self._deliver(DeliveryChannel.SPOKEN, "owner is alone")
            return

        self._go(DueState.CHECK_MEMORY, f"{len(self.detected)} bystander(s) present")
        now = self.ctx.clock.now()
        for key, person in self.detected.items():
            if person.stored:
                self.ctx.repos.bystanders.mark_seen(key, now)
        decision = self._decide()
        if decision is Decision.SPEAK:
            await self._deliver(DeliveryChannel.SPOKEN, "owner allowed these bystanders before")
        elif decision is Decision.SEND_TO_WATCH:
            await self._deliver(DeliveryChannel.WATCH, "owner declined for a bystander before")
        else:
            self._go(DueState.AWAITING_CONSENT, "asking the owner on the watch")
            await self._ask_consent()

    # --- presence -----------------------------------------------------------------------

    async def _owner_present(self) -> bool:
        """The owner wears the watch, so they count as present only while it answers over
        Bluetooth with the consent app loaded. Out of range, or any error, means away."""
        try:
            present = await self.ctx.hardware.watch.ping()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("the watch did not answer (%s): owner treated as away", describe(exc))
            present = False
        self.ctx.bus.emit(EventType.OWNER_PRESENCE, reminder_id=self.reminder.id, present=present)
        return present

    # --- detection ----------------------------------------------------------------------

    def _match(
        self,
        probe: Embedding,
        modality: Biometric,
        owner: list[Embedding],
        known: dict[str, list[Embedding]],
        pending: dict[str, DetectedPerson],
    ) -> Identification:
        """Who ``probe`` is among the owner, remembered bystanders and those found so far."""
        identity = self.settings.identity
        candidates = {
            **known,
            **{k: p.embeddings for k, p in pending.items() if p.source is modality},
        }
        return identify(
            probe,
            modality=modality,
            owner=owner,
            bystanders=candidates,
            threshold=identity.face_threshold
            if modality is Biometric.FACE
            else identity.voice_threshold,
            aggregate=identity.aggregate,
        )

    def _identify(
        self,
        probe: Embedding,
        modality: Biometric,
        owner: list[Embedding],
        known: dict[str, list[Embedding]],
        pending: dict[str, DetectedPerson],
        direction: Direction | None = None,
    ) -> Identification:
        """Record a non-owner in ``pending``. The result's ``bystander_id`` is the key they are
        recorded under."""
        result = self._match(probe, modality, owner, known, pending)
        is_face = modality is Biometric.FACE
        key: str | None = None
        if result.kind is IdentityKind.KNOWN_BYSTANDER and result.bystander_id is not None:
            key = result.bystander_id
            person = pending.setdefault(key, DetectedPerson(key, modality, stored=key in known))
            person.embeddings.append(probe)
        elif result.kind is IdentityKind.NEW_BYSTANDER:
            key = f"new-{next(self._new_ids)}"
            pending[key] = DetectedPerson(key, modality, stored=False, embeddings=[probe])
        self.ctx.bus.emit(
            EventType.FACE_IDENTIFIED if is_face else EventType.VOICE_IDENTIFIED,
            reminder_id=self.reminder.id,
            bystander_id=key,
            identity=result.kind.value,
            similarity=round(result.owner_similarity, 4),
            plugin=self.ctx.perception.plugin_name(
                PluginKind.FACE if is_face else PluginKind.SPEAKER
            ),
            direction=direction.value if direction else None,
        )
        return replace(result, bystander_id=key)

    @staticmethod
    def _describe(result: Identification, known: Mapping[str, object]) -> tuple[str, Tone]:
        """The live view's label for a face or voice (``known``: stored bystanders)."""
        similarity = f"{result.owner_similarity:.2f}"
        if result.kind is IdentityKind.OWNER:
            return f"Owner {similarity}", Tone.OWNER
        if result.bystander_id in known:
            return f"Bystander {result.bystander_id} (owner {similarity})", Tone.OTHER
        return f"Someone else (owner {similarity})", Tone.OTHER

    def _live(self, doing: str) -> AbstractContextManager[None]:
        return self.ctx.live.activity(f"Reminder #{self.reminder.id}: {doing}")

    async def _listen(self, share: float = 1.0) -> bool:
        """Listen until the deadline, for at most ``share`` of the time left; returns whether
        the owner was heard. A voice of someone the owner allowed before (ask-once policy) is
        noted and the robot listens on; it stops once it hears someone it must ask about, or
        someone the owner declined for."""
        ctx, reminder_settings = self.ctx, self.settings.reminder
        until = listen_deadline(
            ctx.clock.now(),
            self.reminder.due_at,
            window=timedelta(minutes=reminder_settings.listen_window_minutes),
            min_listen=timedelta(seconds=reminder_settings.min_listen_seconds),
            until_due=reminder_settings.listen_until_due,
            share=share,
        )
        owner = ctx.repos.owner.embeddings(Biometric.VOICE)
        known = ctx.repos.bystanders.embeddings(Biometric.VOICE)
        safe = self._allowed_before(known)
        pending: dict[str, DetectedPerson] = {}
        heard_owner = False
        non_owner_segments = 0
        needed = self.settings.identity.min_nonowner_segments
        with self._live("listening for other voices"):
            async with aclosing(ctx.speech_segments(until)) as segments:
                async for segment in segments:
                    if segment.duration_s < self.settings.identity.min_voice_segment_seconds:
                        ctx.live.voice(segment.duration_s, "Too short: ignored", Tone.IGNORED)
                        continue
                    probe = await ctx.compute(ctx.perception.speaker.embed, segment)
                    result = self._identify(probe, Biometric.VOICE, owner, known, pending)
                    ctx.live.voice(segment.duration_s, *self._describe(result, known))
                    if result.kind is IdentityKind.OWNER:
                        heard_owner = True
                    elif result.bystander_id not in safe:
                        non_owner_segments += 1
                        if non_owner_segments >= needed:
                            break
        if non_owner_segments >= needed:
            self.detected.update(pending)
        else:  # only people allowed before, if anyone: present all the same, for the decision
            self.detected.update({key: p for key, p in pending.items() if key in safe})
        return heard_owner

    async def _scan(self) -> int:
        """Sweep the room until the due time: each row (``scan.tilts``), every direction
        (``scan.positions``), again and again, each row the other way from the one before
        (``scan_path``). A view that would not end, head back at the front, by the due time is
        not begun, so scanning never makes the reminder late. A face that does not clearly
        match the owner is looked at closer before the sweep goes on (``_study``). Someone the
        owner allowed before (ask-once policy) is noted and the sweep goes on, looking for anyone
        else; once it recognises someone the owner must be asked about, or declined for, the
        scan stops there. The first row is always swept, so a flow that started late still looks
        once. Returns the number of full sweeps."""
        ctx, scan = self.ctx, self.settings.scan
        head, camera = ctx.hardware.head, ctx.hardware.camera
        owner = ctx.repos.owner.embeddings(Biometric.FACE)
        known = ctx.repos.bystanders.embeddings(Biometric.FACE)
        pending: dict[str, DetectedPerson] = {}
        safe = self._allowed_before(known)
        per_sweep = len(scan.tilts) * len(scan.positions)
        started = ctx.clock.now()
        looked = frames = 0
        at: Direction | None = None

        def head_at() -> Direction | None:
            """Where the head points now: the last view's direction (read as each row begins)."""
            return at

        with self._live("scanning the room"):
            await camera.open()
            try:
                # the longest view so far without a closer look; a view begins only if it and
                # the head's way back to the front (no longer than a view) fit before the due time
                view = timedelta(0)
                for tilt, direction in scan_path(scan.tilts, scan.positions, head_at):
                    begun = ctx.clock.now()
                    if any(key not in safe for key in pending) or (
                        looked >= len(scan.positions) and begun + 2 * view > self.reminder.due_at
                    ):
                        break
                    await head.tilt(tilt, scan.head_speed)
                    await head.look(direction, scan.head_speed)
                    await ctx.clock.sleep(scan.settle_seconds)
                    used, closer = await self._look_around(
                        tilt, direction, owner, known, pending, safe
                    )
                    frames += used
                    looked += 1
                    at = direction
                    if not closer:
                        view = max(view, ctx.clock.now() - begun)
            finally:
                await camera.close()
                await head.tilt(Tilt.LEVEL, scan.head_speed)
                await head.look(Direction.FRONT, scan.head_speed)
        self.detected.update(pending)
        sweeps = looked // per_sweep
        ctx.bus.emit(
            EventType.ROOM_SCANNED,
            reminder_id=self.reminder.id,
            count=sweeps,
            frames=frames,
            seconds=round((ctx.clock.now() - started).total_seconds(), 1),
            reason="found someone"
            if any(key not in safe for key in pending)
            else "found only people allowed before"
            if pending
            else "found no one",
        )
        return sweeps

    async def _look_around(
        self,
        tilt: Tilt,
        direction: Direction,
        owner: list[Embedding],
        known: dict[str, list[Embedding]],
        pending: dict[str, DetectedPerson],
        safe: set[str],
    ) -> tuple[int, bool]:
        """Up to ``scan.frames_per_position`` frames in one direction. Faces that match the
        owner, or someone allowed before (``safe``) already recognised in this scan, are noted;
        another face is looked at closer, and that ends this view. Returns the frames analysed,
        and whether it looked closer at a face."""
        ctx, scan = self.ctx, self.settings.scan
        note = f"looking {direction.value}" + (
            f", head {tilt.value}" if tilt is not Tilt.LEVEL else ""
        )
        for count in range(1, scan.frames_per_position + 1):
            frame = await ctx.hardware.camera.grab()
            marks: list[FaceMark] = []
            unclear: list[FaceObservation] = []
            for face in await ctx.compute(ctx.perception.face.detect_and_embed, frame):
                match = self._match(face.embedding, Biometric.FACE, owner, known, pending)
                if match.kind is IdentityKind.OWNER or (
                    match.bystander_id in safe and match.bystander_id in pending
                ):
                    result = self._identify(
                        face.embedding, Biometric.FACE, owner, known, pending, direction
                    )
                    marks.append(FaceMark(face.box, *self._describe(result, known)))
                else:
                    unclear.append(face)
                    marks.append(
                        FaceMark(face.box, "Not recognised yet: looking closer", Tone.IGNORED)
                    )
            ctx.live.face(frame, marks, note=note)
            for number, face in enumerate(unclear):
                if number:  # back to the view the face was seen in
                    await ctx.hardware.head.tilt(tilt, scan.head_speed)
                    await ctx.hardware.head.look(direction, scan.head_speed)
                    await ctx.clock.sleep(scan.settle_seconds)
                result = await self._study(face, frame, direction, note, owner, known, pending)
                if result.kind is not IdentityKind.OWNER and result.bystander_id not in safe:
                    return count, True  # someone to ask about, or declined for: done
            if unclear:  # looking closer took this view's remaining frames
                return count, True
        return scan.frames_per_position, False

    def _view_problems(self, face: FaceObservation, frame: Frame) -> tuple[ViewProblem, ...]:
        if face.box is None:
            return ()
        height, width = frame.image.shape[:2]
        rules = self.settings.scan.follow.full_view()
        return view_problems(face.box, face.score, face.landmarks, (width, height), rules)

    async def _study(
        self,
        face: FaceObservation,
        frame: Frame,
        direction: Direction,
        note: str,
        owner: list[Embedding],
        known: dict[str, list[Embedding]],
        pending: dict[str, DetectedPerson],
    ) -> Identification:
        """Look closer at a face that did not clearly match the owner, and recognise it from
        several views: their average is compared with the owner and the remembered bystanders,
        which evens out one poor frame. With following on, the head turns and nods towards the
        face until it is in full view. It stops after ``scan.study_views`` views in full view,
        after ``scan.study_seconds``, or once the face is lost; then the views so far decide (the
        best one if none was in full view), so a face never seen well still counts."""
        ctx, scan = self.ctx, self.settings.scan
        follow = scan.follow
        head, camera = ctx.hardware.head, ctx.hardware.camera
        started = ctx.clock.now()
        deadline = started + timedelta(seconds=scan.study_seconds)
        turn_gain = -follow.turn_gain if follow.invert_turn else follow.turn_gain
        nod_gain = -follow.nod_gain if follow.invert_nod else follow.nod_gain
        note = f"{note}: looking closer"
        height, width = frame.image.shape[:2]
        size = (width, height)
        current, problems = face, self._view_problems(face, frame)
        views = [(current, problems)]
        # where ``current`` should be in the next frame
        expected = offset(current.box, size) if current.box is not None else (0.0, 0.0)
        moves = misses = 0
        nodded = 0.0
        seen_now = True  # ``current`` is in the latest frame: safe to move towards it

        def clear() -> list[FaceObservation]:
            return [view for view, view_problems in views if not view_problems]

        while (
            len(clear()) < scan.study_views and misses < MAX_MISSES and ctx.clock.now() < deadline
        ):
            if follow.enabled and problems and seen_now and current.box is not None:
                expected = offset(current.box, size)
                turn, nod = head_move(expected, turn_gain=turn_gain, nod_gain=nod_gain)
                if turn or nod:
                    moved = await head.nudge(turn, nod, scan.head_speed)
                    nodded += moved[1]
                    moves += 1
                    expected = after_move(expected, moved, turn_gain=turn_gain, nod_gain=nod_gain)
                    await ctx.clock.sleep(scan.settle_seconds)
            frame = await camera.grab()
            seen = await ctx.compute(ctx.perception.face.detect_and_embed, frame)
            match = _same_face(current, seen, expected, size)
            seen_now = match is not None
            if match is None:
                misses += 1
                ctx.live.face(frame, [], note=f"{note}: lost it")
                continue
            misses = 0
            current, problems = match, self._view_problems(match, frame)
            if current.box is not None:
                expected = offset(current.box, size)
            views.append((current, problems))
            label = (
                f"Not in full view ({', '.join(problems)})"
                if problems
                else f"Looking closer ({len(clear())}/{scan.study_views})"
            )
            ctx.live.face(frame, [FaceMark(current.box, label, Tone.IGNORED)], note=note)
        if nodded:
            await head.nudge(0.0, -nodded, scan.head_speed)
        chosen = clear() or [max(views, key=lambda view: _rank(*view))[0]]
        probe = average([view.embedding for view in chosen])
        result = self._identify(probe, Biometric.FACE, owner, known, pending, direction)
        ctx.live.face(frame, [FaceMark(current.box, *self._describe(result, known))], note=note)
        ctx.bus.emit(
            EventType.FACE_STUDIED,
            reminder_id=self.reminder.id,
            direction=direction.value,
            identity=result.kind.value,
            ready=bool(clear()),
            count=moves,
            frames=len(views),
            seconds=round((ctx.clock.now() - started).total_seconds(), 1),
        )
        return result

    # --- consent ------------------------------------------------------------------------

    def _remember_answer(self, allowed: bool, remembered: dict[str, bool]) -> None:
        """Ask-once policy: store the owner's answer for every bystander that had none.

        A new bystander's embeddings are stored only here, together with a decision , without
        a decision there is no reason to keep them.
        """
        ctx = self.ctx
        now = ctx.clock.now()
        for key, person in list(self.detected.items()):
            if person.stored and key in remembered:
                continue
            bystander_id = key
            if not person.stored:
                bystander = ctx.repos.bystanders.create(
                    person.embeddings[:MAX_STORED_EMBEDDINGS], person.source, now
                )
                bystander_id = bystander.id
                ctx.bus.emit(
                    EventType.BYSTANDER_ENROLLED,
                    reminder_id=self.reminder.id,
                    bystander_id=bystander_id,
                    modality=person.source.value,
                )
            ctx.repos.consents.record(
                bystander_id,
                allowed,
                source=ConsentSource.WATCH,
                now=now,
                reminder_id=self.reminder.id,
            )

    def _allowed_before(self, people: Iterable[str]) -> set[str]:
        """Who among ``people`` (bystander ids) the owner allowed before, under the ask-once
        policy: hearing or seeing them does not end the listening or the scan."""
        if self.settings.privacy.disclosure_policy is not DisclosurePolicy.ASK_ONCE_PER_BYSTANDER:
            return set()
        remembered = self.ctx.repos.consents.effective(people)
        return {key for key, allowed in remembered.items() if allowed}

    def _only_allowed(self) -> bool:
        """Everyone detected so far is someone the owner allowed before."""
        return set(self.detected) <= self._allowed_before(self.detected)

    def _remembered(self) -> dict[str, bool]:
        stored = [k for k, p in self.detected.items() if p.stored]
        return self.ctx.repos.consents.effective(stored)

    def _decide(self) -> Decision:
        privacy = self.settings.privacy
        return decide(
            policy=privacy.disclosure_policy,
            modality=privacy.detection_modality,
            sensitive=self.reminder.sensitive,
            bystanders=list(self.detected),
            remembered=self._remembered(),
        )

    async def _ask_consent(self) -> None:
        ctx, consent = self.ctx, self.settings.consent
        remembered = self._remembered()
        ctx.bus.emit(
            EventType.CONSENT_REQUESTED, reminder_id=self.reminder.id, count=len(self.detected)
        )
        answer = self.answer = await ctx.hardware.watch.prompt(
            consent.prompt_text, consent.timeout_seconds
        )
        ctx.bus.emit(EventType.CONSENT_ANSWERED, reminder_id=self.reminder.id, answer=answer.value)
        ask_once = (
            self.settings.privacy.disclosure_policy is DisclosurePolicy.ASK_ONCE_PER_BYSTANDER
        )
        if ask_once and answer is not WatchAnswer.TIMEOUT:
            self._remember_answer(answer is WatchAnswer.YES, remembered)
        if answer is WatchAnswer.YES:
            await self._deliver(DeliveryChannel.SPOKEN, "owner said yes")
        elif answer is WatchAnswer.NO:
            await self._deliver(DeliveryChannel.WATCH, "owner said no")
        else:
            await self._deliver(DeliveryChannel.WATCH, "no answer: keeping it private")

    # --- delivery -----------------------------------------------------------------------

    async def _deliver(self, channel: DeliveryChannel, reason: str) -> None:
        ctx, reminder = self.ctx, self.reminder
        self.channel = self.planned = channel
        self._go(DueState.WAIT_FOR_DUE, reason)
        await ctx.clock.sleep_until(reminder.due_at)
        due_reason = "due now"
        if channel is DeliveryChannel.SPOKEN and not await self._owner_present():
            # the owner may have left while the robot waited: never speak to an empty room
            self.channel = channel = DeliveryChannel.WATCH
            due_reason = "due now, but the owner's watch did not answer"
        if channel is DeliveryChannel.SPOKEN:
            self._go(DueState.DISCLOSE_SPEAK, due_reason)
            await ctx.hardware.speaker.say(f"Here is your reminder: {reminder.title}.")
            status = ReminderStatus.SPOKEN
        else:
            self._go(DueState.DISCLOSE_WATCH, due_reason)
            await ctx.hardware.watch.notify(f"Reminder: {reminder.title}")
            status = ReminderStatus.SENT_TO_WATCH
        self._mark_delivered(status, channel)
        await ctx.hardware.head.pose(Pose.REST)
        self._go(DueState.DONE, "delivered")

    def _mark_delivered(self, status: ReminderStatus, channel: DeliveryChannel) -> None:
        ctx = self.ctx
        now = ctx.clock.now()
        ctx.repos.reminders.set_status(self.reminder.id, status, delivered_at=now)
        self.delivered = channel
        ctx.bus.emit(
            EventType.REMINDER_DELIVERED,
            reminder_id=self.reminder.id,
            channel=channel.value,
            late_seconds=round(max(0.0, (now - self.reminder.due_at).total_seconds()), 1),
        )

    async def _fail_closed(self) -> None:
        ctx = self.ctx
        try:
            await ctx.clock.sleep_until(self.reminder.due_at)
            await ctx.hardware.watch.notify(f"Reminder: {self.reminder.title}")
            self.channel = DeliveryChannel.WATCH
            self._mark_delivered(ReminderStatus.SENT_TO_WATCH, DeliveryChannel.WATCH)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(  # shown as the pipeline's "missed" toast
                "could not deliver reminder %s to the watch",
                self.reminder.id,
                extra={"toast": False},
            )
            self.channel = None
            ctx.repos.reminders.set_status(self.reminder.id, ReminderStatus.MISSED)
            ctx.bus.emit(
                EventType.REMINDER_MISSED, reminder_id=self.reminder.id, reason="watch unreachable"
            )
        try:
            await ctx.hardware.head.pose(Pose.REST)
        except Exception:
            logger.exception("could not rest the head")


SIDE = {Direction.LEFT: -1, Direction.FRONT: 0, Direction.RIGHT: 1}
"""Where each direction lies across the room, to tell which end of a row is nearer."""


def scan_path(
    tilts: Sequence[Tilt],
    positions: Sequence[Direction],
    where: Callable[[], Direction | None],
) -> Iterator[tuple[Tilt, Direction]]:
    """The room scan's views, row after row without end. Each row starts from its end nearest
    to where the head points as the row begins (``where``), so between rows the head only nods
    and never swings back across the room, whatever came before: the last row, a closer look at
    a face, a sweep with an odd number of rows. With both ends as near (or the head nowhere
    yet), the row goes in the order of ``positions``."""
    first, last = positions[0], positions[-1]
    for tilt in itertools.cycle(tilts):
        at = where()
        reverse = at is not None and abs(SIDE[last] - SIDE[at]) < abs(SIDE[first] - SIDE[at])
        for direction in positions[::-1] if reverse else positions:
            yield tilt, direction


def _same_face(
    target: FaceObservation,
    seen: Sequence[FaceObservation],
    expected: tuple[float, float],
    size: tuple[int, int],
) -> FaceObservation | None:
    """The face in a new frame that is the one being followed: the most similar, if it is
    similar enough to be the same person; else the one nearest to where the head's move should
    have brought it, if near enough (a cut-off face and its full view can differ a lot)."""
    similar = max(seen, key=lambda face: cosine(target.embedding, face.embedding), default=None)
    if similar is not None and cosine(target.embedding, similar.embedding) >= SAME_FACE:
        return similar
    placed = [(math.dist(offset(f.box, size), expected), f) for f in seen if f.box is not None]
    if not placed:
        return None
    distance, nearest = min(placed, key=lambda pair: pair[0])
    return nearest if distance <= NEAR else None


def _rank(face: FaceObservation, problems: Sequence[ViewProblem]) -> tuple[int, float]:
    """Better views rank higher: fewer problems, then a wider and more confident face."""
    width = face.box[2] - face.box[0] if face.box is not None else 0.0
    return -len(problems), face.score * width
