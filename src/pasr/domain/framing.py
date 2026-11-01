"""Whether a face is in full view of the head camera, and how far to move the head to centre it.

Pure geometry on a detector's box and landmarks, in pixels of the frame. The camera sits in the
head, so turning or nodding the head moves a face across the image.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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
    (lx, ly), (rx, ry), (nx, ny) = landmarks[:3]
    ex, ey = rx - lx, ry - ly
    gap = ex * ex + ey * ey
    if gap == 0:
        return math.inf  # both eyes on one point: a full profile
    return abs((nx - (lx + rx) / 2) * ex + (ny - (ly + ry) / 2) * ey) / gap


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
