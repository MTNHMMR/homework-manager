import pytest

from app.assignments import create_assignment, get_assignment_by_id
from app.classes import create_class
from app.users import create_user


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def test_admin_dashboard_requires_admin(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/admin")
    assert resp.status_code == 403


def test_admin_dashboard_requires_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_dashboard_shows_all_kids_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Kid1 Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Kid2 Lab", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "Kid1 Worksheet" in resp.text
    assert "Kid2 Lab" in resp.text


def test_admin_dashboard_groups_assignments_by_kid(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Bob Lab", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert resp.status_code == 200
    # Alice's heading and assignment appear before Bob's (display-name order)
    alice_pos = resp.text.index("Alice")
    bob_pos = resp.text.index("Bob")
    assert alice_pos < bob_pos
    assert "Alice Worksheet" in resp.text
    assert "Bob Lab" in resp.text


def test_admin_dashboard_omits_kid_with_no_matching_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Worksheet", "2026-09-25", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Lab", "2026-09-26", status="not_started")

    _login(client, "parent1")
    resp = client.get("/admin?status=not_started")
    assert "Bob" in resp.text
    assert "Bob Lab" in resp.text
    assert "Alice" not in resp.text


def test_admin_dashboard_kid_id_query_param_is_ignored(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin?kid_id=999")
    assert resp.status_code == 200
    assert "Worksheet" in resp.text


def test_admin_dashboard_marks_overdue_not_done_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Overdue HW", "2020-01-01")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="overdue"' in resp.text


def test_admin_dashboard_does_not_mark_done_assignment_overdue(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Finished HW", "2020-01-01", status="done")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="overdue"' not in resp.text


def test_admin_dashboard_hides_done_assignment_once_due_date_arrives(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Finished Past HW", "2020-01-01", status="done")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert "Finished Past HW" not in resp.text


def test_admin_dashboard_keeps_done_assignment_before_its_due_date(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Finished Early HW", "2099-01-01", status="done")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert "Finished Early HW" in resp.text


def test_admin_dashboard_filters_by_status(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Done One", "2026-09-25", status="done")
    create_assignment(db, kid1.id, "Math", "Pending One", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin?status=done")
    assert "Done One" in resp.text
    assert "Pending One" not in resp.text


def test_admin_can_update_any_assignment_status(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.post(f"/admin/{assignment.id}/status", data={"status": "done"})
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id).status == "done"


def test_admin_can_delete_any_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.post(f"/admin/{assignment.id}/delete")
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id) is None


def test_admin_status_update_on_missing_assignment_is_404(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post("/admin/999/status", data={"status": "done"})
    assert resp.status_code == 404


def test_admin_dashboard_reset_status_filter_shows_everyone(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Done One", "2026-09-25", status="done")
    create_assignment(db, kid1.id, "Math", "Pending One", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin?status=")
    assert resp.status_code == 200
    assert "Done One" in resp.text
    assert "Pending One" in resp.text


@pytest.mark.parametrize(
    "path,data",
    [
        ("/admin/1/status", {"status": "done"}),
        ("/admin/1/delete", None),
    ],
)
def test_admin_mutation_routes_reject_non_admin(client, db, path, data):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(path, data=data or {})
    assert resp.status_code == 403


def test_admin_edit_page_renders_for_any_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.get(f"/admin/{assignment.id}/edit")
    assert resp.status_code == 200
    assert "Math" in resp.text
    assert "Worksheet" in resp.text
    assert "2026-09-25" in resp.text


def test_admin_edit_page_404_for_missing_assignment(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.get("/admin/999/edit")
    assert resp.status_code == 404


def test_admin_edit_updates_any_assignment_including_status(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Science",
            "title": "Lab Report",
            "due_date": "2026-10-01",
            "status": "done",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin"

    updated = get_assignment_by_id(db, assignment.id)
    assert updated.subject == "Science"
    assert updated.title == "Lab Report"
    assert updated.due_date == "2026-10-01"
    assert updated.status == "done"


def test_admin_edit_rejects_invalid_status(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Science",
            "title": "Lab Report",
            "due_date": "2026-10-01",
            "status": "not-a-real-status",
        },
    )
    assert resp.status_code == 400


def test_admin_add_edit_with_missing_field_reenders_form_with_error(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={"subject": "Science", "due_date": "2026-10-01", "status": "done"},
    )
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]
    assert "required" in resp.text.lower()

    unchanged = get_assignment_by_id(db, assignment.id)
    assert unchanged.subject == "Math"
    assert unchanged.title == "Worksheet"
    assert unchanged.due_date == "2026-09-25"
    assert unchanged.status == "not_started"


def test_admin_edit_shows_dropdown_for_kid_with_active_classes(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.get(f"/admin/{assignment.id}/edit")
    assert '<select name="subject"' in resp.text


def test_admin_edit_rejects_subject_not_in_kids_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Gym",
            "title": "Worksheet",
            "due_date": "2026-09-25",
            "status": "not_started",
        },
    )
    assert resp.status_code == 400


def test_admin_dashboard_shows_admin_owned_assignments_in_their_own_section(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Worksheet", "2026-09-25")
    _login(client, "parent1")
    # Parent logs an assignment for themself via their own overview page.
    client.post(
        "/overview/add",
        data={"subject": "Errands", "title": "Buy poster board", "due_date": "2026-09-25"},
    )

    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "Alice Worksheet" in resp.text
    assert "Buy poster board" in resp.text
    assert "Parent One" in resp.text


def test_admin_dashboard_shows_priority_marker(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Big Test", "2026-09-25", priority=True)
    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="priority-mark"' in resp.text


def test_admin_dashboard_sorts_priority_assignments_first_within_kid(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Sooner Regular", "2026-09-20")
    create_assignment(db, kid1.id, "Science", "Later Important", "2026-09-26", priority=True)
    _login(client, "parent1")
    resp = client.get("/admin")
    assert resp.text.index("Later Important") < resp.text.index("Sooner Regular")


def test_admin_edit_can_toggle_priority(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Math",
            "title": "Worksheet",
            "due_date": "2026-09-25",
            "status": "not_started",
            "priority": "1",
        },
    )
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id).priority is True


def test_admin_history_requires_admin(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/admin/history")
    assert resp.status_code == 403


def test_admin_history_requires_login(client):
    resp = client.get("/admin/history")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_history_shows_all_kids_completed_assignments_grouped(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Finished", "2020-01-01", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Finished", "2020-01-02", status="done")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert resp.status_code == 200
    assert "Alice Finished" in resp.text
    assert "Bob Finished" in resp.text


def test_admin_history_excludes_not_done_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Still Working HW", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert "Still Working HW" not in resp.text


def test_admin_history_omits_kid_with_no_completed_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Finished", "2020-01-01", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Not Done", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert "Alice" in resp.text
    assert "Bob" not in resp.text


def test_admin_dashboard_shows_kid_streak(client, db):
    from datetime import date, timedelta

    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assignment = create_assignment(db, kid1.id, "Math", "Yesterday HW", yesterday, status="done")
    db.execute(
        "UPDATE assignments SET completed_at = ? WHERE id = ?",
        (f"{yesterday} 10:00:00", assignment.id),
    )
    db.commit()
    _login(client, "parent1")
    resp = client.get("/admin")
    assert "1-day streak" in resp.text
