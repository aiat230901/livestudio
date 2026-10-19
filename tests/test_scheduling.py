from datetime import datetime

import pytest

from desktop.scheduling import VN_TZ, next_window, normalize_schedule


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=VN_TZ).timestamp()


def once(start, end):
    return dict(kind="once", start=at(start), end=at(end))


def weekly(days, start=22 * 60, end=2 * 60):
    return dict(kind="weekly", days=days, start_minute=start, end_minute=end)


def test_once_start_inclusive_end_exclusive_and_no_backfill():
    rule = once("2026-10-19T09:00", "2026-10-19T10:00")
    assert next_window([rule], at("2026-10-19T08:59")) == (rule["start"], rule["end"])
    assert next_window([rule], rule["start"]) == (rule["start"], rule["end"])
    assert next_window([rule], rule["end"]) is None


def test_weekly_overnight_uses_start_day_and_vietnam_time():
    rule = weekly([0])  # Monday 22:00 -> Tuesday 02:00.
    expected = (at("2026-10-19T22:00"), at("2026-10-20T02:00"))
    assert next_window([rule], at("2026-10-20T01:00")) == expected
    assert next_window([rule], expected[1])[0] == at("2026-10-26T22:00")
    assert datetime.fromtimestamp(expected[0], VN_TZ).hour == 22


def test_overlap_touching_and_week_boundary_merge():
    rules = [
        weekly([6]),
        once("2026-10-19T02:00", "2026-10-19T03:00"),
        weekly([0], 150, 240),
    ]
    assert next_window(rules, at("2026-10-19T01:00")) == (
        at("2026-10-18T22:00"),
        at("2026-10-19T04:00"),
    )


def test_connected_daily_rules_cover_full_week_without_artificial_end():
    rules = [weekly(list(range(7)), 0, 720), weekly(list(range(7)), 720, 0)]
    now = at("2026-10-19T01:00")
    assert next_window(rules, now) == (now, None)


def test_long_once_extends_into_weekly_window_without_scanning_each_day():
    rules = [once("2026-10-19T10:00", "2030-10-21T23:00"), weekly([0])]
    assert next_window(rules, at("2026-10-19T12:00")) == (
        at("2026-10-19T10:00"),
        at("2030-10-22T02:00"),
    )


@pytest.mark.parametrize(
    "rule",
    [
        weekly([], 60, 120),
        weekly([7]),
        weekly([True]),
        weekly([0], 60, 60),
        weekly([0], -1, 60),
        weekly([0], 0, 1440),
        dict(kind="once", start=1, end=1),
        dict(kind="once", start=1, end=float("inf")),
        dict(kind="other"),
    ],
)
def test_invalid_rules_rejected(rule):
    with pytest.raises(ValueError):
        normalize_schedule(rule)
