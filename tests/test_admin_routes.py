from app.assignments import create_assignment, get_assignment_by_id
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


def test_admin_dashboard_filters_by_kid(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Kid1 Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Kid2 Lab", "2026-09-26")

    _login(client, "parent1")
    resp = client.get(f"/admin?kid_id={kid1.id}")
    assert "Kid1 Worksheet" in resp.text
    assert "Kid2 Lab" not in resp.text


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


def test_admin_dashboard_reset_kid_filter_shows_everyone(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Kid1 Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Kid2 Lab", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin?kid_id=")
    assert resp.status_code == 200
    assert "Kid1 Worksheet" in resp.text
    assert "Kid2 Lab" in resp.text


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
