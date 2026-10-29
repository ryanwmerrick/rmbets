from datetime import datetime

from sportpredict.jobs.gate import ET, decide

never_done = lambda since: False  # noqa: E731
always_done = lambda since: True  # noqa: E731


def at(day, hh, mm):
    return datetime(2026, 10, day, hh, mm, tzinfo=ET)


def test_daily_waits_until_830():
    go, wait = decide("daily", at(29, 6, 0), never_done)
    assert go and wait == 150 * 60


def test_daily_too_early_leaves_it_to_a_later_attempt():
    assert decide("daily", at(29, 2, 0), never_done) == (False, 0)


def test_daily_late_runs_immediately_and_done_skips():
    assert decide("daily", at(29, 13, 0), never_done) == (True, 0)
    assert decide("daily", at(29, 13, 0), always_done) == (False, 0)


def test_snapshot_targets_noon_on_sunday_then_afternoon():
    sunday = 25
    go, wait = decide("snapshot", at(sunday, 10, 30), never_done)
    assert go and wait == 120 * 60  # 12:30
    go, wait = decide("snapshot", at(29, 13, 0), never_done)
    assert go and wait == 225 * 60  # Thursday: 4:45 only


def test_snapshot_skips_noon_target_once_done():
    # At 2pm Sunday the noon snapshot is done (since 9:30); next is 4:45
    done_noon = lambda since: since.hour == 9  # noqa: E731
    go, wait = decide("snapshot", at(25, 14, 0), done_noon)
    assert go and wait == 165 * 60
