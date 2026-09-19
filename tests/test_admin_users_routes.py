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
