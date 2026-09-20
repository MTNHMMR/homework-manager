from app.assignments import create_assignment
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
