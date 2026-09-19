from app.users import create_user


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Log in" in resp.text


def test_login_success_sets_session_and_redirects_kid_to_overview(client, db):
    create_user(db, "kid1", "hunter2", "Kid One")
    resp = client.post("/login", data={"username": "kid1", "password": "hunter2"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/overview"


def test_login_success_redirects_admin_to_admin_dashboard(client, db):
    create_user(db, "parent1", "hunter2", "Parent One", is_admin=True)
    resp = client.post("/login", data={"username": "parent1", "password": "hunter2"})
    assert resp.headers["location"] == "/admin"


def test_login_failure_shows_generic_error(client, db):
    create_user(db, "kid1", "hunter2", "Kid One")
    resp = client.post("/login", data={"username": "kid1", "password": "wrong"})
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.text


def test_login_failure_for_unknown_user_shows_same_generic_error(client):
    resp = client.post("/login", data={"username": "nobody", "password": "wrong"})
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.text


def test_login_rejects_deactivated_user(client, db):
    from app.users import set_user_active

    user = create_user(db, "kid1", "hunter2", "Kid One")
    set_user_active(db, user.id, False)
    resp = client.post("/login", data={"username": "kid1", "password": "hunter2"})
    assert resp.status_code == 401


def test_logout_clears_session(client, db):
    create_user(db, "kid1", "hunter2", "Kid One")
    client.post("/login", data={"username": "kid1", "password": "hunter2"})
    resp = client.post("/logout")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # session is cleared: hitting a protected page now redirects to /login
    protected = client.get("/overview")
    assert protected.status_code == 303
    assert protected.headers["location"] == "/login"
