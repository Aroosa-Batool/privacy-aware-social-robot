from datetime import UTC, datetime, timedelta

from pasr.domain.timing import flow_start, is_missed, listen_deadline, started_late

DUE = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)
SEC = timedelta(seconds=1)


def test_flow_starts_early_only_when_detection_is_needed():
    assert flow_start(DUE, wake_lead=7 * MIN, needs_detection=True) == DUE - 7 * MIN
    assert flow_start(DUE, wake_lead=7 * MIN, needs_detection=False) == DUE


def test_a_flow_waking_a_moment_after_its_start_time_is_not_late():
    on_time = DUE - 7 * MIN
    assert not started_late(on_time, DUE, wake_lead=7 * MIN)
    assert not started_late(on_time + timedelta(milliseconds=20), DUE, wake_lead=7 * MIN)
    assert started_late(on_time + 5 * SEC, DUE, wake_lead=7 * MIN)
    assert started_late(DUE - 45 * SEC, DUE, wake_lead=7 * MIN)  # a quick test


def deadline(start, *, until_due=False, share=1.0):
    return listen_deadline(
        start,
        DUE,
        window=5 * MIN,
        min_listen=timedelta(seconds=15),
        until_due=until_due,
        share=share,
    )


def test_listening_window_and_until_due():
    start = DUE - 7 * MIN
    assert deadline(start) == start + 5 * MIN
    assert deadline(start, until_due=True) == DUE


def test_window_is_clamped_to_the_due_time():
    start = DUE - 2 * MIN
    assert deadline(start) == DUE


def test_late_start_still_listens_for_the_minimum():
    start = DUE + MIN
    assert deadline(start) == start + timedelta(seconds=15)
    assert deadline(DUE - 10 * SEC, share=0.7) == DUE + 5 * SEC


def test_a_share_leaves_the_rest_of_the_time_left_to_the_camera():
    assert deadline(DUE - 5 * MIN, share=0.7) == DUE - 90 * SEC
    assert deadline(DUE - 50 * SEC, share=0.7) == DUE - 15 * SEC
    assert deadline(DUE - 10 * MIN, share=0.7) == DUE - 5 * MIN  # never past the window
    assert deadline(DUE - 5 * MIN, until_due=True, share=0.7) == DUE


def test_missed_after_grace():
    assert not is_missed(DUE, DUE + 9 * MIN, grace=10 * MIN)
    assert is_missed(DUE, DUE + 11 * MIN, grace=10 * MIN)
