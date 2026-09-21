from dataclasses import dataclass
from datetime import date

from app.weeks import current_week_start, group_assignments_by_day, week_dates


def test_current_week_start_on_sunday_returns_same_day():
    assert current_week_start(date(2026, 9, 20)) == date(2026, 9, 20)  # a Sunday


def test_current_week_start_on_wednesday_returns_preceding_sunday():
    assert current_week_start(date(2026, 9, 23)) == date(2026, 9, 20)  # a Wednesday


def test_current_week_start_on_saturday_returns_preceding_sunday():
    assert current_week_start(date(2026, 9, 26)) == date(2026, 9, 20)  # a Saturday


def test_week_dates_returns_seven_consecutive_days_from_sunday():
    dates = week_dates(date(2026, 9, 20))
    assert dates == [date(2026, 9, 20 + i) for i in range(7)]


def test_group_assignments_by_day_buckets_by_due_date():
    @dataclass
    class FakeAssignment:
        due_date: str

    dates = week_dates(date(2026, 9, 20))
    assignments = [FakeAssignment(due_date="2026-09-22"), FakeAssignment(due_date="2026-09-22")]
    grouped = group_assignments_by_day(assignments, dates)

    assert len(grouped) == 7
    tuesday_date, tuesday_items = grouped[2]
    assert tuesday_date == date(2026, 9, 22)
    assert len(tuesday_items) == 2
    monday_date, monday_items = grouped[1]
    assert monday_date == date(2026, 9, 21)
    assert monday_items == []
