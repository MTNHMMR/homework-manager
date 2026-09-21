from app.assignments import create_assignment, get_assignment_by_id, list_assignments_for_user
from app.classes import create_class
from app.users import create_user


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def test_overview_requires_login(client):
    resp = client.get("/overview")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_overview_lists_only_own_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_assignment(db, kid1.id, "Math", "Kid1 Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Kid2 Lab", "2026-09-26")

    _login(client, "kid1")
    resp = client.get("/overview")
    assert resp.status_code == 200
    assert "Kid1 Worksheet" in resp.text
    assert "Kid2 Lab" not in resp.text


def test_add_assignment_creates_it_for_current_user(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add",
        data={"subject": "Math", "title": "New Worksheet", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/overview"

    listing = client.get("/overview")
    assert "New Worksheet" in listing.text


def test_set_status_updates_own_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")

    resp = client.post(f"/overview/{assignment.id}/status", data={"status": "done"})
    assert resp.status_code == 303

    from app.assignments import get_assignment_by_id

    assert get_assignment_by_id(db, assignment.id).status == "done"


def test_cannot_change_status_of_another_users_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    assignment = create_assignment(db, kid2.id, "Science", "Lab", "2026-09-26")

    _login(client, "kid1")
    resp = client.post(f"/overview/{assignment.id}/status", data={"status": "done"})
    assert resp.status_code == 403


def test_delete_own_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")

    resp = client.post(f"/overview/{assignment.id}/delete")
    assert resp.status_code == 303

    from app.assignments import get_assignment_by_id

    assert get_assignment_by_id(db, assignment.id) is None


def test_cannot_delete_another_users_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    assignment = create_assignment(db, kid2.id, "Science", "Lab", "2026-09-26")

    _login(client, "kid1")
    resp = client.post(f"/overview/{assignment.id}/delete")
    assert resp.status_code == 403

    from app.assignments import get_assignment_by_id

    assert get_assignment_by_id(db, assignment.id) is not None


def test_edit_page_renders_for_own_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")

    resp = client.get(f"/overview/{assignment.id}/edit")
    assert resp.status_code == 200
    assert "Math" in resp.text
    assert "Worksheet" in resp.text
    assert "2026-09-25" in resp.text


def test_edit_page_403_for_another_users_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    assignment = create_assignment(db, kid2.id, "Science", "Lab", "2026-09-26")

    _login(client, "kid1")
    resp = client.get(f"/overview/{assignment.id}/edit")
    assert resp.status_code == 403


def test_edit_updates_own_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")

    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Science", "title": "Lab Report", "due_date": "2026-10-01"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/overview"

    from app.assignments import get_assignment_by_id

    updated = get_assignment_by_id(db, assignment.id)
    assert updated.subject == "Science"
    assert updated.title == "Lab Report"
    assert updated.due_date == "2026-10-01"
    assert updated.status == "not_started"


def test_edit_403_for_another_users_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    assignment = create_assignment(db, kid2.id, "Science", "Lab", "2026-09-26")

    _login(client, "kid1")
    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Hacked", "title": "Hacked", "due_date": "2026-10-01"},
    )
    assert resp.status_code == 403

    from app.assignments import get_assignment_by_id

    unchanged = get_assignment_by_id(db, assignment.id)
    assert unchanged.subject == "Science"
    assert unchanged.title == "Lab"


def test_add_assignment_with_missing_title_reenders_form_with_error(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")

    resp = client.post(
        "/overview/add",
        data={"subject": "Math", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]
    assert "required" in resp.text.lower()

    from app.assignments import list_assignments_for_user

    assert list_assignments_for_user(db, kid.id) == []


def test_add_assignment_shows_dropdown_when_active_classes_exist(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert '<select name="subject"' in resp.text


def test_add_assignment_shows_free_text_when_no_active_classes(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'type="text" name="subject"' in resp.text


def test_add_assignment_accepts_subject_from_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.post(
        "/overview/add", data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25"}
    )
    assert resp.status_code == 303


def test_add_assignment_rejects_subject_not_in_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.post(
        "/overview/add", data={"subject": "Gym", "title": "Worksheet", "due_date": "2026-09-25"}
    )
    assert resp.status_code == 400

    from app.assignments import list_assignments_for_user

    assert list_assignments_for_user(db, kid.id) == []


def test_add_assignment_allows_free_text_when_no_active_classes(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add",
        data={"subject": "Anything", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 303


def test_edit_page_shows_dropdown_when_active_classes_exist(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.get(f"/overview/{assignment.id}/edit")
    assert '<select name="subject"' in resp.text


def test_edit_rejects_subject_not_in_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Gym", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 400


def test_overview_marks_overdue_not_done_assignment_with_overdue_class(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Overdue HW", "2020-01-01")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' in resp.text


def test_overview_does_not_mark_done_assignment_overdue(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' not in resp.text


def test_overview_does_not_mark_future_assignment_overdue(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Future HW", "2099-01-01")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' not in resp.text


def test_overview_marks_overdue_in_progress_assignment_too(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Started HW", "2020-01-01", status="in_progress")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' in resp.text


def test_add_assignment_validation_error_does_not_crash_when_kid_has_existing_assignments(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Existing Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add", data={"subject": "Math", "title": "", "due_date": "2026-09-25"}
    )
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]
    assert "required" in resp.text.lower()


def test_overview_does_not_mark_assignment_due_today_as_overdue(client, db):
    from datetime import date

    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Due Today HW", date.today().isoformat())
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' not in resp.text


def test_overview_hides_done_assignment_once_due_date_arrives(client, db):
    from datetime import date

    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(
        db, kid.id, "Math", "Finished Past HW", "2020-01-01", status="done"
    )
    create_assignment(
        db, kid.id, "Math", "Finished Today HW", date.today().isoformat(), status="done"
    )
    _login(client, "kid1")
    resp = client.get("/overview")
    assert "Finished Past HW" not in resp.text
    assert "Finished Today HW" not in resp.text


def test_overview_keeps_done_assignment_before_its_due_date(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(
        db, kid.id, "Math", "Finished Early HW", "2099-01-01", status="done"
    )
    _login(client, "kid1")
    resp = client.get("/overview")
    assert "Finished Early HW" in resp.text


def test_overview_keeps_not_done_assignment_past_due_date_and_turns_it_red(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Still Overdue HW", "2020-01-01")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert "Still Overdue HW" in resp.text
    assert 'class="overdue"' in resp.text


def test_add_assignment_with_priority_checked_persists_it(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add",
        data={"subject": "Math", "title": "Big Test", "due_date": "2026-09-25", "priority": "1"},
    )
    assert resp.status_code == 303
    assignments = list_assignments_for_user(db, kid.id)
    assert assignments[0].priority is True


def test_add_assignment_without_priority_defaults_false(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    client.post(
        "/overview/add",
        data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assignments = list_assignments_for_user(db, kid.id)
    assert assignments[0].priority is False


def test_overview_shows_priority_marker_for_flagged_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Big Test", "2026-09-25", priority=True)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="priority-mark"' in resp.text


def test_overview_sorts_priority_assignments_first(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Sooner Regular", "2026-09-20")
    create_assignment(db, kid.id, "Science", "Later Important", "2026-09-26", priority=True)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert resp.text.index("Later Important") < resp.text.index("Sooner Regular")


def test_edit_assignment_can_toggle_priority(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25", "priority": "1"},
    )
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id).priority is True


def test_overview_history_requires_login(client):
    resp = client.get("/overview/history")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_overview_history_shows_own_completed_assignments(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert resp.status_code == 200
    assert "Finished HW" in resp.text


def test_overview_history_excludes_not_done_assignments(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Still Working HW", "2026-09-25")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert "Still Working HW" not in resp.text


def test_overview_history_excludes_other_kids_completed_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_assignment(db, kid2.id, "Math", "Other Kid HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert "Other Kid HW" not in resp.text


def test_overview_history_has_edit_link(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert f'/overview/{assignment.id}/edit' in resp.text
