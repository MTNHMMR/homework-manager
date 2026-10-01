import pytest

from app.users import create_user, get_user_by_id, get_user_by_username


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def test_manage_users_requires_admin(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/admin/users")
    assert resp.status_code == 403


def test_manage_users_lists_everyone(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.get("/admin/users")
    assert "Kid One" in resp.text
    assert "Parent One" in resp.text


def test_add_user_creates_new_kid(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        "/admin/users/add",
        data={"username": "kid2", "password": "kidpass", "display_name": "Kid Two"},
    )
    assert resp.status_code == 303
    created = get_user_by_username(db, "kid2")
    assert created is not None
    assert created.is_admin is False


def test_add_user_can_create_another_admin(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        "/admin/users/add",
        data={
            "username": "parent2",
            "password": "pw2",
            "display_name": "Parent Two",
            "is_admin": "on",
        },
    )
    assert resp.status_code == 303
    created = get_user_by_username(db, "parent2")
    assert created.is_admin is True


def test_add_user_rejects_duplicate_username(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "parent1")
    resp = client.post(
        "/admin/users/add",
        data={"username": "kid1", "password": "pw2", "display_name": "Kid One Again"},
    )
    assert resp.status_code == 400


def test_reset_password_lets_user_log_in_with_new_password(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "oldpw", "Kid One")
    _login(client, "parent1")

    resp = client.post(
        f"/admin/users/{kid.id}/reset-password", data={"new_password": "newpw"}
    )
    assert resp.status_code == 303

    client.post("/logout")
    login_resp = client.post("/login", data={"username": "kid1", "password": "newpw"})
    assert login_resp.status_code == 303
    assert login_resp.headers["location"] == "/overview"


def test_deactivate_user_prevents_login(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "parent1")

    resp = client.post(f"/admin/users/{kid.id}/deactivate")
    assert resp.status_code == 303
    assert get_user_by_id(db, kid.id).active is False

    client.post("/logout")
    login_resp = client.post("/login", data={"username": "kid1", "password": "pw"})
    assert login_resp.status_code == 401


def test_activate_user_restores_login(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "parent1")

    client.post(f"/admin/users/{kid.id}/deactivate")
    resp = client.post(f"/admin/users/{kid.id}/activate")
    assert resp.status_code == 303
    assert get_user_by_id(db, kid.id).active is True


def test_cannot_deactivate_last_active_admin(client, db):
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(f"/admin/users/{admin.id}/deactivate")
    assert resp.status_code == 400
    from app.users import get_user_by_id

    assert get_user_by_id(db, admin.id).active is True


def test_can_deactivate_an_admin_when_another_admin_is_active(client, db):
    admin1 = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_user(db, "parent2", "pw", "Parent Two", is_admin=True)
    _login(client, "parent1")
    resp = client.post(f"/admin/users/{admin1.id}/deactivate")
    assert resp.status_code == 303
    from app.users import get_user_by_id

    assert get_user_by_id(db, admin1.id).active is False


def test_edit_user_can_promote_to_admin(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    parent2 = create_user(db, "parent2", "pw", "Parent Two")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/users/{parent2.id}/edit",
        data={"username": "parent2", "display_name": "Parent Two", "is_admin": "on"},
    )
    assert resp.status_code == 303
    assert get_user_by_id(db, parent2.id).is_admin is True


def test_edit_user_renames(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/users/{kid.id}/edit", data={"username": "kiddo", "display_name": "Kiddo"}
    )
    assert resp.status_code == 303
    updated = get_user_by_id(db, kid.id)
    assert (updated.username, updated.display_name, updated.is_admin) == ("kiddo", "Kiddo", False)


def test_edit_user_form_shows_current_values(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "parent1")
    resp = client.get(f"/admin/users/{kid.id}/edit")
    assert resp.status_code == 200
    assert 'value="kid1"' in resp.text
    assert 'value="Kid One"' in resp.text


def test_edit_user_rejects_taken_username(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "kid2", "pw", "Kid Two")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/users/{kid.id}/edit", data={"username": "kid2", "display_name": "Kid One"}
    )
    assert resp.status_code == 400
    assert get_user_by_id(db, kid.id).username == "kid1"


def test_edit_user_cannot_demote_last_active_admin(client, db):
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post(
        f"/admin/users/{admin.id}/edit", data={"username": "parent1", "display_name": "Parent One"}
    )
    assert resp.status_code == 400
    assert get_user_by_id(db, admin.id).is_admin is True


def test_delete_user_removes_user_and_their_data(client, db):
    from app.assignments import create_assignment, list_assignments_for_user
    from app.classes import list_active_classes_for_user

    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Worksheet", "2026-10-05")
    db.execute("INSERT INTO classes (user_id, name) VALUES (?, ?)", (kid.id, "Math"))
    db.commit()
    _login(client, "parent1")

    resp = client.post(f"/admin/users/{kid.id}/delete")
    assert resp.status_code == 303
    assert get_user_by_id(db, kid.id) is None
    assert list_assignments_for_user(db, kid.id) == []
    assert list_active_classes_for_user(db, kid.id) == []


def test_delete_user_cannot_delete_self(client, db):
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_user(db, "parent2", "pw", "Parent Two", is_admin=True)
    _login(client, "parent1")
    resp = client.post(f"/admin/users/{admin.id}/delete")
    assert resp.status_code == 400
    assert get_user_by_id(db, admin.id) is not None


def test_delete_user_can_delete_another_admin(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    other = create_user(db, "parent2", "pw", "Parent Two", is_admin=True)
    _login(client, "parent1")
    resp = client.post(f"/admin/users/{other.id}/delete")
    assert resp.status_code == 303
    assert get_user_by_id(db, other.id) is None


@pytest.mark.parametrize(
    "path,data",
    [
        ("/admin/users/add", {"username": "x", "password": "y", "display_name": "z"}),
        ("/admin/users/1/reset-password", {"new_password": "q"}),
        ("/admin/users/1/deactivate", None),
        ("/admin/users/1/activate", None),
        ("/admin/users/1/edit", {"username": "x", "display_name": "z"}),
        ("/admin/users/1/delete", None),
    ],
)
def test_admin_user_mutation_routes_reject_non_admin(client, db, path, data):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(path, data=data or {})
    assert resp.status_code == 403
