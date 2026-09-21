import pytest

from app.assignments import (
    VALID_STATUSES,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    list_assignments_for_user,
    update_assignment,
)


def test_create_assignment_defaults_to_not_started(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Ch. 4 worksheet", "2026-09-25")
    assert assignment.status == "not_started"
    assert assignment.user_id == kid.id


def test_create_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    with pytest.raises(ValueError):
        create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="graded")


def test_get_assignment_by_id_roundtrip(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert get_assignment_by_id(db, created.id) == created


def test_get_assignment_by_id_missing_returns_none(db):
    assert get_assignment_by_id(db, 999) is None


def test_list_assignments_for_user_only_returns_that_user(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Lab report", "2026-09-26")

    kid1_assignments = list_assignments_for_user(db, kid1.id)
    assert len(kid1_assignments) == 1
    assert kid1_assignments[0].subject == "Math"


def test_list_assignments_for_user_sorted_by_due_date(db, make_user):
    kid = make_user("kid1")
    create_assignment(db, kid.id, "Math", "Later", "2026-10-01")
    create_assignment(db, kid.id, "Math", "Sooner", "2026-09-20")
    titles = [a.title for a in list_assignments_for_user(db, kid.id)]
    assert titles == ["Sooner", "Later"]


def test_list_all_assignments_spans_users(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Lab report", "2026-09-26")
    assert len(list_all_assignments(db)) == 2


def test_update_assignment_changes_fields(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).status == "done"


def test_update_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    with pytest.raises(ValueError):
        update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "graded", False)


def test_delete_assignment_removes_it(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    delete_assignment(db, created.id)
    assert get_assignment_by_id(db, created.id) is None


def test_valid_statuses_constant():
    assert VALID_STATUSES == ("not_started", "in_progress", "done")


def test_create_assignment_defaults_priority_false(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert assignment.priority is False


def test_create_assignment_accepts_priority_true(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", priority=True)
    assert assignment.priority is True


def test_create_assignment_sets_completed_at_when_created_done(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    assert assignment.completed_at is not None


def test_create_assignment_leaves_completed_at_none_when_not_done(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert assignment.completed_at is None


def test_update_assignment_sets_completed_at_when_marked_done(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).completed_at is not None


def test_update_assignment_clears_completed_at_when_changed_away_from_done(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "in_progress", False)
    assert get_assignment_by_id(db, created.id).completed_at is None


def test_update_assignment_keeps_completed_at_on_noop_done_update(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    original_completed_at = get_assignment_by_id(db, created.id).completed_at
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).completed_at == original_completed_at


def test_update_assignment_persists_priority(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "not_started", True)
    assert get_assignment_by_id(db, created.id).priority is True
