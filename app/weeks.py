from datetime import date, timedelta


def current_week_start(today: date) -> date:
    """Sunday of the week containing `today`."""
    return today - timedelta(days=(today.weekday() + 1) % 7)


def week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def group_assignments_by_day(assignments, dates: list[date]) -> list[tuple[date, list]]:
    by_date: dict[str, list] = {}
    for a in assignments:
        by_date.setdefault(a.due_date, []).append(a)
    return [(d, by_date.get(d.isoformat(), [])) for d in dates]
