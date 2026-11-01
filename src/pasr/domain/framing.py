"""Whether a face is in full view of the head camera, which way it points, and how far to move
the head to centre it.

Pure geometry on a detector's box and landmarks, in pixels of the frame. The camera sits in the
head, so turning or nodding the head moves a face across the image.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pasr.domain.enums import FacePose

Box = tuple[float, float, float, float]
"""(x1, y1, x2, y2) in pixels."""
Point = tuple[float, float]

CENTRED = 0.15
"""A face this close to the image centre (as a share of half the image) is centred: the head
does not move for less, so it never jitters around a face."""


class ViewProblem(StrEnum):
    CUT_OFF = "cut off"
    SMALL = "too small"
    UNCLEAR = "unclear"
    TURNED_AWAY = "turned away"


@dataclass(frozen=True, slots=True)
class FullView:
    """What a face needs to count as in full view."""

    min_width_px: float
    min_score: float
    edge_margin: float
    """Share of the image's width (height) a face must keep from the side (top, bottom) edges."""
    max_turned: float
    """See ``turned``."""


def turned(landmarks: Sequence[Point]) -> float:
    """How far a face is turned away from the camera: the nose tip's distance from the point
    between the eyes, along the line through the eyes, as a share of the eye distance. 0 faces
    the camera; about 0.5 is half profile. ``landmarks`` start with both eyes and the nose tip."""
    return abs(yaw(landmarks))


def yaw(landmarks: Sequence[Point]) -> float:
    """``turned`` with a sign: positive when the nose tip is off towards the second eye."""
    (lx, ly), (rx, ry), (nx, ny) = landmarks[:3]
    ex, ey = rx - lx, ry - ly
    gap = ex * ex + ey * ey
    if gap == 0:
        return math.inf  # both eyes on one point: a full profile
    return ((nx - (lx + rx) / 2) * ex + (ny - (ly + ry) / 2) * ey) / gap


def tilt(landmarks: Sequence[Point]) -> float:
    """Where the nose tip sits between the eyes and the mouth: its distance from the line through
    the eyes as a share of the mouth's (the middle of its corners). It falls as the chin goes up
    and rises as it goes down; its value for a level face differs between people and with the
    camera's height. ``landmarks`` are both eyes, the nose tip and both mouth corners."""
    (lx, ly), (rx, ry), (nx, ny), (ax, ay), (bx, by) = landmarks[:5]
    ex, ey = rx - lx, ry - ly  # across the eye line is (-ey, ex)
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    mouth = ((ax + bx) / 2 - cx) * -ey + ((ay + by) / 2 - cy) * ex
    if mouth == 0:
        return math.inf  # the mouth on the eye line: no face
    return ((nx - cx) * -ey + (ny - cy) * ex) / mouth


FRONT_MAX_TURN = 0.12
"""Looking straight at the camera: ``turned`` at most this (about 15°)."""
SIDE_TURN = (0.15, 0.8)
"""Turned left or right: ``turned`` between these (about 17° to 60°; further, a face's
landmarks and embedding become unreliable)."""
MIN_TILT = 0.05
"""Chin up or down: ``tilt`` at least this far from the straight-ahead faces' (about 10°)."""
OPPOSITE = {
    FacePose.LEFT: FacePose.RIGHT,
    FacePose.RIGHT: FacePose.LEFT,
    FacePose.UP: FacePose.DOWN,
    FacePose.DOWN: FacePose.UP,
}


class PoseMiss(StrEnum):
    """Why a face does not point the way the owner was asked to look."""

    TURNED = "turned"
    """Turned sideways (asked to look straight, or to tilt the chin)."""
    TOO_LITTLE = "too little"
    TOO_FAR = "too far"
    WRONG_WAY = "wrong way"
    """The way the opposite pose's faces point."""
    NO_LEVEL = "no straight view"
    """Up or down before any straight-ahead face to measure them from."""


@dataclass(slots=True)
class PoseCheck:
    """Whether faces point the way the owner was asked to look, for guided enrolment. Which side
    of the image is the owner's left is not assumed (a mirrored camera works too): all faces of
    a pose point the same way, the opposite of the opposite pose's, and up and down are measured
    from the straight-ahead faces, so ``front`` must come before them."""

    level: list[float] = field(default_factory=list)
    """``tilt`` of the straight-ahead faces taken."""
    signs: dict[FacePose, float] = field(default_factory=dict)
    """Which way (±1) the faces of each other pose point."""

    def miss(self, pose: FacePose, landmarks: Sequence[Point] | None) -> PoseMiss | None:
        """Why a face does not point the way ``pose`` asks; ``None`` if it does, and then it
        counts as one of the pose's faces. Without the landmarks needed to tell, every face
        does."""
        tilting = pose in (FacePose.UP, FacePose.DOWN)
        if landmarks is None or len(landmarks) < (5 if tilting else 3):
            return None
        turn = yaw(landmarks)
        if pose is FacePose.FRONT:
            if abs(turn) > FRONT_MAX_TURN:
                return PoseMiss.TURNED
            level = tilt(landmarks) if len(landmarks) >= 5 else math.inf
            if math.isfinite(level):
                self.level.append(level)
            return None
        if not tilting:
            if abs(turn) < SIDE_TURN[0]:
                return PoseMiss.TOO_LITTLE
            if abs(turn) > SIDE_TURN[1]:
                return PoseMiss.TOO_FAR
            return self._this_way(pose, turn)
        moved = self.tilted(landmarks)
        if moved is None:
            return PoseMiss.NO_LEVEL
        if abs(turn) > SIDE_TURN[1]:
            return PoseMiss.TURNED
        if abs(moved) < MIN_TILT:
            return PoseMiss.TOO_LITTLE
        return self._this_way(pose, moved)

    def tilted(self, landmarks: Sequence[Point]) -> float | None:
        """How far ``tilt`` is from the straight-ahead faces'; ``None`` before any of them, or
        without mouth corners."""
        if not self.level or len(landmarks) < 5:
            return None
        moved = tilt(landmarks) - statistics.median(self.level)
        return moved if math.isfinite(moved) else None

    def _this_way(self, pose: FacePose, value: float) -> PoseMiss | None:
        sign = math.copysign(1.0, value)
        if self.signs.get(pose, sign) != sign or self.signs.get(OPPOSITE[pose]) == sign:
            return PoseMiss.WRONG_WAY
        self.signs[pose] = sign
        return None


def view_problems(
    box: Box,
    score: float,
    landmarks: Sequence[Point] | None,
    size: tuple[int, int],
    rules: FullView,
) -> tuple[ViewProblem, ...]:
    """Why a face in a ``size`` (width, height) frame is not in full view; empty when it is.
    Without landmarks, a face is never judged turned away."""
    width, height = size
    x1, y1, x2, y2 = box
    margin_x, margin_y = rules.edge_margin * width, rules.edge_margin * height
    problems = []
    if x1 < margin_x or y1 < margin_y or x2 > width - margin_x or y2 > height - margin_y:
        problems.append(ViewProblem.CUT_OFF)
    if x2 - x1 < rules.min_width_px:
        problems.append(ViewProblem.SMALL)
    if score < rules.min_score:
        problems.append(ViewProblem.UNCLEAR)
    if landmarks is not None and len(landmarks) >= 3 and turned(landmarks) > rules.max_turned:
        problems.append(ViewProblem.TURNED_AWAY)
    return tuple(problems)


def offset(box: Box, size: tuple[int, int]) -> tuple[float, float]:
    """Where the face's centre is in a ``size`` (width, height) frame: -1 at the left (top)
    edge, 0 at the centre, 1 at the right (bottom) edge."""
    width, height = size
    x1, y1, x2, y2 = box
    return (x1 + x2) / width - 1, (y1 + y2) / height - 1


def head_move(
    position: tuple[float, float], *, turn_gain: float, nod_gain: float
) -> tuple[float, float]:
    """HEADTURN and HEADNOD steps (motor units) that bring a face at ``position`` (see
    ``offset``) to the image centre. The gains are the steps for a face at the side and top
    edges: positive turns towards a higher HEADTURN for a face right of centre and nods towards
    a higher HEADNOD for a face above it; negative the other way round."""
    dx, dy = position
    turn = turn_gain * dx if abs(dx) > CENTRED else 0.0
    nod = -nod_gain * dy if abs(dy) > CENTRED else 0.0
    return turn, nod


def after_move(
    position: tuple[float, float],
    moved: tuple[float, float],
    *,
    turn_gain: float,
    nod_gain: float,
) -> tuple[float, float]:
    """Where a face at ``position`` should be once the head turned and nodded by ``moved``,
    by the same gains as ``head_move`` (a face it does not move for stays where it is)."""
    (dx, dy), (turned_by, nodded_by) = position, moved
    return (
        dx - turned_by / turn_gain if turn_gain else dx,
        dy + nodded_by / nod_gain if nod_gain else dy,
    )
