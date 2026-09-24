from app.classes import create_class, get_class_by_id, list_classes_for_user
from app.users import create_user


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def test_manage_classes_requires_admin(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/admin/classes")
    assert resp.status_code == 403


def test_manage_classes_lists_kid_classes(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_class(db, kid.id, "Science", teacher="Rogers", period=2)
    _login(client, "parent1")
    resp = client.get("/admin/classes")
    assert resp.status_code == 200
    assert "Science" in resp.text
    assert "Rogers" in resp.text


def test_add_class_creates_it(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        "/admin/classes/add",
        data={
            "user_id": str(kid.id),
            "name": "Math",
            "teacher": "Smith",
            "period": "1",
            "expires_on": "2026-12-31",
        },
    )
    assert resp.status_code == 303
    classes = list_classes_for_user(db, kid.id)
    assert len(classes) == 1
    assert classes[0].name == "Math"
    assert classes[0].expires_on == "2026-12-31"


def test_add_class_without_optional_fields(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        "/admin/classes/add",
        data={"user_id": str(kid.id), "name": "A+ Tutoring"},
    )
    assert resp.status_code == 303
    classes = list_classes_for_user(db, kid.id)
    assert classes[0].teacher is None
    assert classes[0].period is None
    assert classes[0].expires_on is None


def test_edit_class_page_renders(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    c = create_class(db, kid.id, "Math", period=1)
    _login(client, "parent1")
    resp = client.get(f"/admin/classes/{c.id}/edit")
    assert resp.status_code == 200
    assert "Math" in resp.text


def test_edit_class_updates_it(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    c = create_class(db, kid.id, "Math", period=1)
    _login(client, "parent1")
    resp = client.post(
        f"/admin/classes/{c.id}/edit",
        data={
            "name": "Advanced Math",
            "teacher": "Smith",
            "period": "2",
            "expires_on": "2026-12-31",
        },
    )
    assert resp.status_code == 303
    updated = get_class_by_id(db, c.id)
    assert updated.name == "Advanced Math"
    assert updated.teacher == "Smith"
    assert updated.period == 2


def test_edit_class_404_for_missing(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post("/admin/classes/999/edit", data={"name": "X"})
    assert resp.status_code == 404


def test_delete_class_removes_it(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    c = create_class(db, kid.id, "Math")
    _login(client, "parent1")
    resp = client.post(f"/admin/classes/{c.id}/delete")
    assert resp.status_code == 303
    assert get_class_by_id(db, c.id) is None


def test_admin_classes_mutation_routes_reject_non_admin(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    c = create_class(db, kid.id, "Math")
    _login(client, "kid1")
    assert client.post(
        "/admin/classes/add", data={"user_id": str(kid.id), "name": "X"}
    ).status_code == 403
    assert client.get(f"/admin/classes/{c.id}/edit").status_code == 403
    assert client.post(f"/admin/classes/{c.id}/edit", data={"name": "X"}).status_code == 403
    assert client.post(f"/admin/classes/{c.id}/delete").status_code == 403


def test_add_class_rejects_blank_name(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        "/admin/classes/add", data={"user_id": str(kid.id), "name": "   "}
    )
    assert resp.status_code == 400
    from app.classes import list_classes_for_user

    assert list_classes_for_user(db, kid.id) == []


def test_edit_class_rejects_blank_name(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    c = create_class(db, kid.id, "Math", period=1)
    _login(client, "parent1")
    resp = client.post(f"/admin/classes/{c.id}/edit", data={"name": "   "})
    assert resp.status_code == 400
    from app.classes import get_class_by_id

    unchanged = get_class_by_id(db, c.id)
    assert unchanged.name == "Math"


def test_add_class_404_for_nonexistent_user(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post("/admin/classes/add", data={"user_id": "999", "name": "Math"})
    assert resp.status_code == 404



def test_add_class_rejects_admin_target(client, db):
    admin = create_user(db, "parent-target", "pw", "Parent Target", is_admin=True)
    create_user(db, "parent-login", "pw", "Parent Login", is_admin=True)
    _login(client, "parent-login")
    resp = client.post(
        "/admin/classes/add", data={"user_id": str(admin.id), "name": "Math"}
    )
    assert resp.status_code == 400
    assert list_classes_for_user(db, admin.id) == []


def test_add_class_rejects_malformed_expiration_date(client, db):
    kid = create_user(db, "class-date-kid", "pw", "Class Date Kid")
    create_user(db, "class-date-admin", "pw", "Class Date Admin", is_admin=True)
    _login(client, "class-date-admin")
    resp = client.post(
        "/admin/classes/add",
        data={"user_id": str(kid.id), "name": "Math", "expires_on": "2026-02-31"},
    )
    assert resp.status_code == 400
    assert list_classes_for_user(db, kid.id) == []
