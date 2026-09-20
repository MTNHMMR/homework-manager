from app.users import create_user, get_user_by_id


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def test_settings_requires_login(client):
    resp = client.get("/settings")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_page_shows_current_theme(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert 'name="theme" value="light" checked' in resp.text


def test_settings_updates_theme_and_accent(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post("/settings", data={"theme": "dark", "accent_color": "teal"})
    assert resp.status_code == 303
    updated = get_user_by_id(db, kid.id)
    assert updated.theme == "dark"
    assert updated.accent_color == "teal"


def test_settings_rejects_invalid_theme(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post("/settings", data={"theme": "neon", "accent_color": "blue"})
    assert resp.status_code == 400
    updated = get_user_by_id(db, kid.id)
    assert updated.theme == "light"


def test_settings_only_changes_own_account(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    _login(client, "kid1")
    client.post("/settings", data={"theme": "dark", "accent_color": "teal"})
    assert get_user_by_id(db, kid2.id).theme == "light"
