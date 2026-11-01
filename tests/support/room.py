"""A scripted stand-in for the physical room, used only by the tests: who is speaking, who is
visible where, and what the robot and watch did.

The stand-in devices (``devices.py``) and perception plugins (``perception.py``) read and write
this state; tests and the scenario runner script it. All methods must be called on the
runtime's event-loop thread.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pasr.domain.enums import Direction, WatchAnswer
from pasr.orchestration.clock import Clock

OWNER_TAG = "owner"
"""Identity tag of the owner in test scripts."""

CURRENT: Room | None = None
"""The most recently created room. Stand-in perception plugins are built by the registry from
their Params alone, so they find the room here."""

FIELD_OF_VIEW = (2.5, 1.5)
"""Motor units (HEADTURN, HEADNOD) from the image centre to its side (top) edge. Equal to the
default ``scan.follow`` gains, so one head move centres a face that was fully in view."""
MIN_VISIBLE = 0.2
"""A face with less of it inside the image is not detected."""


@dataclass(frozen=True, slots=True)
class Spot:
    """Where a face appears while the head looks straight at its direction: ``x``/``y`` from -1
    (left/top edge) to 1 (right/bottom edge), ``size`` its width as a share of the image's, and
    ``turned`` how far it is turned away (``pasr.domain.framing.turned``)."""

    x: float = 0.0
    y: float = 0.0
    size: float = 0.3
    turned: float = 0.0


@dataclass(frozen=True, slots=True)
class SeenFace:
    """A face as the head camera sees it: its box clipped to the image, its landmarks, and its
    ``clarity`` (1 in full view; lower makes its embedding less like the person's)."""

    tag: str
    box: tuple[float, float, float, float]
    landmarks: tuple[tuple[float, float], ...]
    clarity: float


@dataclass(frozen=True, slots=True)
class Utterance:
    speaker: str
    start: datetime
    end: datetime
    text: str | None = None


@dataclass(frozen=True, slots=True)
class ScriptedAnswer:
    answer: WatchAnswer
    delay_s: float


@dataclass(slots=True)
class PendingPrompt:
    id: int
    text: str
    future: asyncio.Future[WatchAnswer] = field(repr=False)


@dataclass(frozen=True, slots=True)
class LogLine:
    at: datetime
    text: str


class Room:
    def __init__(self, clock: Clock) -> None:
        global CURRENT
        CURRENT = self
        self.clock = clock
        self.utterances: list[Utterance] = []
        self.faces: dict[Direction, list[str]] = {d: [] for d in Direction}
        self.faces[Direction.FRONT].append(OWNER_TAG)
        self.spots: dict[str, Spot] = {}
        """Where each person's face appears; a centred, front-facing face if not listed."""
        self.head_direction = Direction.FRONT
        self.head_offset = (0.0, 0.0)
        """How far the head turned (HEADTURN) and nodded (HEADNOD) since it looked in its
        direction and took its pose."""
        self.field_of_view = FIELD_OF_VIEW
        self.camera_on = False
        self.camera_opened = 0
        self.camera_grabs = 0
        self.microphone_opened = 0
        self.owner_away: list[tuple[datetime, datetime | None]] = []
        """When the owner, wearing the watch, is out of Bluetooth range (end ``None``: open)."""
        self.spoken: deque[LogLine] = deque(maxlen=200)
        self.watch_notifications: deque[LogLine] = deque(maxlen=200)
        self.watch_prompts: deque[LogLine] = deque(maxlen=200)
        self.pending_prompt: PendingPrompt | None = None
        self.scripted_answers: deque[ScriptedAnswer] = deque()
        self._prompt_ids = itertools.count(1)

    # --- people -------------------------------------------------------------------------

    def speak(
        self,
        speaker: str,
        seconds: float,
        *,
        text: str | None = None,
        start: datetime | None = None,
    ) -> Utterance:
        begin = start or self.clock.now()
        utterance = Utterance(speaker, begin, begin + timedelta(seconds=seconds), text)
        self.utterances.append(utterance)
        self.utterances.sort(key=lambda u: u.start)
        return utterance

    def voice_at(self, moment: datetime) -> Utterance | None:
        for utterance in self.utterances:
            if utterance.start <= moment < utterance.end:
                return utterance
        return None

    def set_faces(self, direction: Direction, people: list[str]) -> None:
        self.faces[direction] = list(dict.fromkeys(people))

    def place(self, person: str, **spot: float) -> None:
        """Where ``person``'s face appears in their direction (see ``Spot``)."""
        self.spots[person] = Spot(**spot)

    def in_view(self, width: int, height: int) -> tuple[SeenFace, ...]:
        """The faces a ``width`` x ``height`` head camera sees, given where the head points."""
        turn, nod = self.head_offset
        span_turn, span_nod = self.field_of_view
        seen = []
        for person in self.faces[self.head_direction]:
            spot = self.spots.get(person, Spot())
            # turning right moves faces left in the image; nodding up moves them down
            cx = (spot.x - turn / span_turn + 1) * width / 2
            cy = (spot.y + nod / span_nod + 1) * height / 2
            half_w = spot.size * width / 2
            half_h = 1.2 * half_w
            x1, y1, x2, y2 = cx - half_w, cy - half_h, cx + half_w, cy + half_h
            box = (max(x1, 0.0), max(y1, 0.0), min(x2, float(width)), min(y2, float(height)))
            inside = max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)
            visible = inside / ((x2 - x1) * (y2 - y1))
            if visible < MIN_VISIBLE:
                continue
            eye_y, half_eyes = cy - 0.3 * half_h, 0.4 * half_w
            landmarks = (
                (cx - half_eyes, eye_y),
                (cx + half_eyes, eye_y),
                (cx + spot.turned * 2 * half_eyes, cy),  # the nose tip
                (cx - half_eyes, cy + 0.5 * half_h),
                (cx + half_eyes, cy + 0.5 * half_h),
            )
            clarity = visible * (1 - min(spot.turned, 1.0) / 2)
            seen.append(SeenFace(person, box, landmarks, clarity))
        return tuple(seen)

    def stage_owner(self, *, voice_samples: int, segment_s: float = 2.0) -> None:
        """Put the owner in front of the robot, talking, so enrolment has something to capture."""
        if OWNER_TAG not in self.faces[Direction.FRONT]:
            self.faces[Direction.FRONT].append(OWNER_TAG)
        self.stage_speaker(OWNER_TAG, samples=voice_samples, segment_s=segment_s)

    def clear_upcoming(self) -> None:
        """Drop utterances that have not started yet (e.g. before staging someone else)."""
        now = self.clock.now()
        self.utterances = [u for u in self.utterances if u.start <= now]

    def stage_speaker(self, speaker: str, *, samples: int, segment_s: float = 2.0) -> None:
        """Schedule ``samples + 1`` separate utterances by ``speaker``, starting shortly."""
        start = self.clock.now() + timedelta(seconds=0.5)
        for i in range(samples + 1):
            self.speak(speaker, segment_s, start=start + timedelta(seconds=i * (segment_s + 1)))

    def leave(self, start: datetime | None = None, back: datetime | None = None) -> None:
        """The owner walks out of Bluetooth range with the watch, until ``back`` (if given)."""
        self.owner_away.append((start or self.clock.now(), back))

    # --- watch --------------------------------------------------------------------------

    def watch_in_range(self) -> bool:
        now = self.clock.now()
        return not any(
            start <= now and (back is None or now < back) for start, back in self.owner_away
        )

    def open_prompt(self, text: str, timeout_s: float) -> PendingPrompt:
        now = self.clock.now()
        future: asyncio.Future[WatchAnswer] = asyncio.get_running_loop().create_future()
        prompt = PendingPrompt(next(self._prompt_ids), text, future)
        self.pending_prompt = prompt
        self.watch_prompts.append(LogLine(now, text))
        return prompt

    def answer(self, prompt_id: int, answer: WatchAnswer) -> bool:
        prompt = self.pending_prompt
        if prompt is None or prompt.id != prompt_id or prompt.future.done():
            return False
        prompt.future.set_result(answer)
        return True

    def close_prompt(self, prompt: PendingPrompt) -> None:
        if self.pending_prompt is prompt:
            self.pending_prompt = None

    def script_answer(self, answer: WatchAnswer, delay_s: float = 3.0) -> None:
        self.scripted_answers.append(ScriptedAnswer(answer, delay_s))

    # --- bookkeeping --------------------------------------------------------------------

    def clear_logs(self) -> None:
        self.camera_opened = self.camera_grabs = self.microphone_opened = 0
        self.spoken.clear()
        self.watch_notifications.clear()
        self.watch_prompts.clear()
