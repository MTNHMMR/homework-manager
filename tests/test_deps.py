from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.deps import get_current_user, require_admin, require_user
from app.users import create_user


def _build_test_app(db_path):
    app = FastAPI()
    app.state.db_path = str(db_path)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.post("/set-session/{user_id}")
    def set_session(user_id: int, request: Request):
        request.session["user_id"] = user_id
        return {"ok": True}

    @app.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"user_id": user.id if user else None}

    @app.get("/protected")
    def protected(user=Depends(require_user)):
        return {"ok": True}

    @app.get("/admin-only")
    def admin_only(user=Depends(require_admin)):
        return {"ok": True}

    return app


def test_get_current_user_none_when_not_logged_in(db_path):
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    resp = client.get("/whoami")
    assert resp.json() == {"user_id": None}


def test_get_current_user_returns_logged_in_user(db_path, db):
    user = create_user(db, "kid1", "pw", "Kid One")
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    client.post(f"/set-session/{user.id}")
    resp = client.get("/whoami")
    assert resp.json() == {"user_id": user.id}


def test_require_user_redirects_to_login_when_not_logged_in(db_path):
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    resp = client.get("/protected")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_require_user_allows_logged_in_user(db_path, db):
    user = create_user(db, "kid1", "pw", "Kid One")
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    client.post(f"/set-session/{user.id}")
    resp = client.get("/protected")
    assert resp.status_code == 200


def test_require_admin_rejects_non_admin(db_path, db):
    user = create_user(db, "kid1", "pw", "Kid One", is_admin=False)
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    client.post(f"/set-session/{user.id}")
    resp = client.get("/admin-only")
    assert resp.status_code == 403


def test_require_admin_allows_admin(db_path, db):
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    client = TestClient(_build_test_app(db_path), follow_redirects=False)
    client.post(f"/set-session/{admin.id}")
    resp = client.get("/admin-only")
    assert resp.status_code == 200
