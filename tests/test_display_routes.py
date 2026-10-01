from datetime import date, timedelta

import pytest

from app.assignments import create_assignment
from app.display_tokens import create_display_token, list_display_tokens
from app.users import create_user


def _login(client, username, password="pw"):
    client.post("/login", data={"username": username, "password": password})


def _days(n):
    return (date.today() + timedelta(days=n)).isoformat()


def _get(client, token, **params):
    return client.get(
        "/api/display/assignments",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_feed_rejects_missing_token(client, db):
    assert client.get("/api/display/assignments").status_code == 401


def test_feed_rejects_wrong_token(client, db):
    create_display_token(db, "Wall")
    assert _get(client, "not-a-real-token").status_code == 401


def test_feed_rejects_revoked_token(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    record, token = create_display_token(db, "Wall")
    _login(client, "parent1")
    client.post(f"/admin/display/tokens/{record.id}/revoke")
    assert _get(client, token).status_code == 401


def test_feed_returns_upcoming_and_overdue_grouped_by_kid(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "kid2", "pw", "Kid Two")
    create_assignment(db, kid.id, "Math", "Late worksheet", _days(-1))
    create_assignment(db, kid.id, "Science", "Lab", _days(2), priority=True)
    create_assignment(db, kid.id, "English", "Essay", _days(20))
    create_assignment(db, kid.id, "Art", "Finished", _days(1), status="done")
    _, token = create_display_token(db, "Wall")

    resp = _get(client, token)
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"] == date.today().isoformat()
    kids = {k["name"]: k["assignments"] for k in body["kids"]}
    # Admins without homework are left off; kids with nothing due still appear.
    assert set(kids) == {"Kid One", "Kid Two"}
    assert kids["Kid Two"] == []
    titles = [a["title"] for a in kids["Kid One"]]
    assert titles == ["Late worksheet", "Lab"]
    assert kids["Kid One"][0]["overdue"] is True
    assert kids["Kid One"][1]["priority"] is True


def test_feed_days_param_widens_window(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "English", "Essay", _days(20))
    _, token = create_display_token(db, "Wall")
    titles = [a["title"] for a in _get(client, token, days=21).json()["kids"][0]["assignments"]]
    assert titles == ["Essay"]


def test_feed_skips_inactive_users(client, db):
    from app.users import set_user_active

    kid = create_user(db, "kid1", "pw", "Kid One")
    set_user_active(db, kid.id, False)
    _, token = create_display_token(db, "Wall")
    assert _get(client, token).json()["kids"] == []


def test_feed_records_last_used(client, db):
    _, token = create_display_token(db, "Wall")
    _get(client, token)
    assert list_display_tokens(db)[0].last_used_at is not None


def test_admin_can_create_token_and_it_is_shown_once(client, db):
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    _login(client, "parent1")
    resp = client.post("/admin/display/tokens", data={"name": "Kitchen"})
    assert resp.status_code == 200
    assert "won't be shown again" in resp.text
    assert [t.name for t in list_display_tokens(db)] == ["Kitchen"]
    page = client.get("/admin/display")
    assert "Kitchen" in page.text
    assert "won't be shown again" not in page.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/display"),
        ("post", "/admin/display/tokens"),
        ("post", "/admin/display/tokens/1/revoke"),
    ],
)
def test_display_admin_routes_reject_non_admin(client, db, method, path):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = getattr(client, method)(path, **({"data": {"name": "x"}} if method == "post" else {}))
    assert resp.status_code == 403
