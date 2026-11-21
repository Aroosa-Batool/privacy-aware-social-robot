"""Whether a face is in full view, and how the head moves to centre it."""

import math

import pytest

from pasr.domain.enums import FacePose
from pasr.domain.framing import (
    CENTRED,
    FullView,
    PoseCheck,
    PoseMiss,
    ViewProblem,
    after_move,
    head_move,
    offset,
    tilt,
    turned,
    view_problems,
    yaw,
)

SIZE = (640, 480)
RULES = FullView(min_width_px=60, min_score=0.7, edge_margin=0.03, max_turned=0.4)
FRONTAL = ((290.0, 220.0), (350.0, 220.0), (320.0, 250.0), (295.0, 280.0), (345.0, 280.0))


def problems(box, score=0.9, landmarks=FRONTAL):
    return view_problems(box, score, landmarks, SIZE, RULES)


def posed(turn: float = 0.0, chin: float = 0.0):
    """``FRONTAL`` with the nose tip moved ``turn`` eye distances sideways and ``chin`` times
    the eye-to-mouth distance down."""
    left, right, (nx, ny), *mouth = FRONTAL
    return (left, right, (nx + turn * 60, ny + chin * 60), *mouth)


def test_a_centred_frontal_face_is_in_full_view():
    assert problems((270, 180, 370, 300)) == ()


@pytest.mark.parametrize(
    "box",
    [(0, 180, 100, 300), (560, 180, 640, 300), (270, 0, 370, 120), (270, 400, 370, 480)],
    ids=["left", "right", "top", "bottom"],
)
def test_a_face_at_an_edge_may_be_cut_off(box):
    assert problems(box) == (ViewProblem.CUT_OFF,)


def test_small_unclear_and_turned_away_faces():
    assert problems((300, 220, 340, 260)) == (ViewProblem.SMALL,)
    assert problems((270, 180, 370, 300), score=0.5) == (ViewProblem.UNCLEAR,)
    profile = ((290.0, 220.0), (350.0, 220.0), (360.0, 250.0))
    assert problems((270, 180, 370, 300), landmarks=profile) == (ViewProblem.TURNED_AWAY,)
    assert problems((270, 180, 370, 300), landmarks=None) == ()  # no landmarks: not judged
    assert problems((0, 0, 30, 30), score=0.2) == (
        ViewProblem.CUT_OFF,
        ViewProblem.SMALL,
        ViewProblem.UNCLEAR,
    )


def test_turned_measures_the_nose_along_the_eye_line():
    assert turned(FRONTAL) == 0
    assert turned(((0.0, 0.0), (60.0, 0.0), (60.0, 30.0))) == pytest.approx(0.5)
    tilted = ((0.0, 0.0), (60.0, 60.0), (20.0, 40.0))  # head tilted 45°, nose under the middle
    assert turned(tilted) == pytest.approx(0)
    assert turned(((10.0, 10.0), (10.0, 10.0), (12.0, 20.0))) == math.inf


def test_yaw_keeps_the_side_and_tilt_places_the_nose_between_eyes_and_mouth():
    assert yaw(posed(0.3)) == pytest.approx(0.3)
    assert yaw(posed(-0.3)) == pytest.approx(-0.3) and turned(posed(-0.3)) == pytest.approx(0.3)
    assert tilt(FRONTAL) == pytest.approx(0.5)
    assert tilt(posed(chin=-0.1)) == pytest.approx(0.4)
    rolled = ((0.0, 0.0), (60.0, 60.0), (10.0, 50.0), (-20.0, 60.0), (0.0, 80.0))  # 45° roll
    assert tilt(rolled) == pytest.approx(0.5)
    assert tilt(((0.0, 0.0), (60.0, 0.0), (30.0, 0.0), (0.0, 0.0), (60.0, 0.0))) == math.inf


def test_each_pose_takes_only_faces_pointing_its_way_and_says_why_not():
    check = PoseCheck()
    assert check.miss(FacePose.FRONT, posed(0.3)) is PoseMiss.TURNED
    assert check.miss(FacePose.FRONT, FRONTAL) is None and check.level == [pytest.approx(0.5)]
    assert check.miss(FacePose.LEFT, posed(0.1)) is PoseMiss.TOO_LITTLE
    assert check.miss(FacePose.LEFT, posed(0.9)) is PoseMiss.TOO_FAR  # unreliable that far
    assert check.miss(FacePose.LEFT, posed(-0.3)) is None  # either side may be the left...
    assert check.miss(FacePose.LEFT, posed(0.3)) is PoseMiss.WRONG_WAY  # ...then always it
    assert check.miss(FacePose.RIGHT, posed(-0.3)) is PoseMiss.WRONG_WAY
    assert check.miss(FacePose.RIGHT, posed(0.3)) is None
    assert check.miss(FacePose.UP, posed(chin=-0.03)) is PoseMiss.TOO_LITTLE
    assert check.miss(FacePose.UP, posed(0.9, chin=-0.1)) is PoseMiss.TURNED
    assert check.miss(FacePose.UP, posed(chin=-0.1)) is None
    assert check.miss(FacePose.DOWN, posed(chin=-0.1)) is PoseMiss.WRONG_WAY
    assert check.miss(FacePose.DOWN, posed(chin=0.1)) is None


def test_up_and_down_need_straight_ahead_faces_and_without_landmarks_any_face_counts():
    check = PoseCheck()
    assert check.miss(FacePose.UP, posed(chin=-0.1)) is PoseMiss.NO_LEVEL
    assert check.miss(FacePose.UP, None) is None and check.miss(FacePose.LEFT, None) is None
    assert check.miss(FacePose.UP, FRONTAL[:3]) is None  # no mouth corners: tilt is unknown
    assert check.signs == {} and check.tilted(FRONTAL) is None
    assert check.miss(FacePose.FRONT, FRONTAL) is None
    assert check.tilted(posed(chin=0.1)) == pytest.approx(0.1)


def test_offset_runs_from_edge_to_edge():
    assert offset((270, 190, 370, 290), SIZE) == (0, 0)
    assert offset((540, 0, 640, 100), SIZE) == pytest.approx((0.84375, -0.79167), abs=1e-4)


def test_the_head_moves_towards_the_face_and_not_for_a_centred_one():
    assert head_move((0.8, -0.5), turn_gain=2.5, nod_gain=1.5) == pytest.approx((2.0, 0.75))
    assert head_move((-0.8, 0.5), turn_gain=-2.5, nod_gain=-1.5) == pytest.approx((2.0, 0.75))
    assert head_move((CENTRED, -CENTRED), turn_gain=2.5, nod_gain=1.5) == (0, 0)


def test_after_a_full_move_the_face_is_expected_at_the_centre():
    for position in [(0.8, -0.5), (-0.6, 0.9)]:
        moved = head_move(position, turn_gain=2.5, nod_gain=1.5)
        assert after_move(position, moved, turn_gain=2.5, nod_gain=1.5) == pytest.approx((0, 0))
    half_way = after_move((0.8, -0.5), (1.0, 0.0), turn_gain=2.5, nod_gain=1.5)
    assert half_way == pytest.approx((0.4, -0.5))  # a move cut short at the motor's end
    assert after_move((0.8, -0.5), (0.0, 0.0), turn_gain=0, nod_gain=0) == (0.8, -0.5)
