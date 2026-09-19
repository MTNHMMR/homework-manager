# Homework Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted homework tracker: kids log their own assignments under their own login, admins (any user flagged `is_admin`) see and manage everyone's assignments plus manage user accounts — packaged as a single Docker container.

**Architecture:** FastAPI app with server-rendered Jinja2 templates, SQLite for storage (stdlib `sqlite3`, no ORM), session-cookie auth (`bcrypt` password hashes, `starlette.middleware.sessions`). A thin data-access layer (`app/users.py`, `app/assignments.py`) sits between routers and raw SQL. Permission checks live in FastAPI dependencies (`app/deps.py`) so every route enforces them the same way.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Jinja2, `python-multipart` (form parsing), `bcrypt`, `itsdangerous` (session signing), SQLite, pytest + httpx for tests, Docker/Docker Compose.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-19-homework-manager-design.md`.
- Admin is a boolean flag (`is_admin`) on the `users` table — not a separate account type or table. Any account can be flagged admin.
- Every permission check happens server-side in a route/dependency, never only hidden in the UI. A non-admin touching another user's assignment gets HTTP 403.
- Invalid login returns a generic "invalid username or password" message — never reveal whether the username exists.
- SQLite file path comes from `HOMEWORK_DB_PATH` env var (default `homework.db`), so it can be pointed at a mounted volume in Docker or a temp file in tests.
- Session signing key comes from `SESSION_SECRET_KEY` env var; the app must fail to start if it's unset (no silent insecure default).
- App must not hardcode its own origin/host, and must work correctly behind a reverse proxy later (no functionality in this plan depends on `request.base_url` beyond what Starlette derives from headers).

---

## File Structure

```
app/
  __init__.py
  main.py            # create_app() factory — no import-time side effects
  asgi.py            # `app = create_app()` — the real entrypoint for uvicorn
  database.py         # schema + sqlite3 connection helper
  security.py          # password hashing
  deps.py             # FastAPI dependencies: get_db, get_current_user, require_user, require_admin
  users.py            # users table data access
  assignments.py       # assignments table data access
  routers/
    __init__.py
    auth.py           # /login, /logout, /
    overview.py        # /overview and its actions (kid's own assignments)
    admin.py           # /admin and its actions (all assignments)
    admin_users.py       # /admin/users and its actions
  templates/
    base.html
    login.html
    overview.html
    admin.html
    admin_users.html
  static/
    style.css
scripts/
  bootstrap_admin.py    # creates the first admin from ADMIN_USERNAME/ADMIN_PASSWORD env vars
tests/
  conftest.py
  test_database.py
  test_security.py
  test_users.py
  test_assignments.py
  test_deps.py
  test_auth_routes.py
  test_overview_routes.py
  test_admin_routes.py
  test_admin_users_routes.py
  test_bootstrap.py
requirements.txt
requirements-dev.txt
Dockerfile
docker-compose.yml
.env.example
.gitignore
README.md
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `pytest.ini`
- Create: `app/__init__.py`
- Create: `app/routers/__init__.py`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: a working `pytest` invocation and installable dependency set that every later task relies on.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
jinja2==3.1.4
python-multipart==0.0.12
bcrypt==4.2.0
itsdangerous==2.2.0
```

- [ ] **Step 2: Write `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
*.db
.pytest_cache/
.venv/
venv/
.env
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 5: Create empty package markers**

Create `app/__init__.py`, `app/routers/__init__.py`, `tests/__init__.py` — all empty files.

- [ ] **Step 6: Install dependencies and verify pytest runs**

Run: `pip install -r requirements-dev.txt`
Run: `pytest`
Expected: `pytest` reports "no tests ran" (or similar) with exit code 0 — no import errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore pytest.ini app/__init__.py app/routers/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding and dependencies"
```

---

### Task 2: Database schema and connection helper

**Files:**
- Create: `app/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `get_connection(db_path) -> sqlite3.Connection` (row factory = `sqlite3.Row`), `init_db(conn: sqlite3.Connection) -> None` (creates `users` and `assignments` tables if missing). Every later data-access module depends on these two functions and on the exact column names below.
- `users` columns: `id, username, password_hash, display_name, is_admin, active, created_at`.
- `assignments` columns: `id, user_id, subject, title, due_date, status, created_at`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
import sqlite3
from app.database import get_connection, init_db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"users", "assignments"} <= tables
    conn.close()


def test_get_connection_uses_row_factory(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    assert conn.row_factory is sqlite3.Row
    conn.close()


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_database.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 3: Write the implementation**

```python
# app/database.py
import sqlite3
from pathlib import Path
from typing import Union

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_database.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: sqlite schema and connection helper"
```

---

### Task 3: Password hashing

**Files:**
- Create: `app/security.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`. Used by `app/users.py` (Task 4) and login route (Task 7).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security.py
from app.security import hash_password, verify_password


def test_verify_password_accepts_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_password_does_not_return_plaintext():
    hashed = hash_password("my-password")
    assert hashed != "my-password"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.security'`

- [ ] **Step 3: Write the implementation**

```python
# app/security.py
import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_security.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/security.py tests/test_security.py
git commit -m "feat: bcrypt password hashing"
```

---

### Task 4: Users data access

**Files:**
- Create: `app/users.py`
- Test: `tests/test_users.py`
- Modify: `tests/conftest.py` (create — shared fixtures start here)

**Interfaces:**
- Consumes: `get_connection`, `init_db` (Task 2); `hash_password` (Task 3).
- Produces: `User` dataclass (`id: int, username: str, password_hash: str, display_name: str, is_admin: bool, active: bool`); `create_user(conn, username, password, display_name, is_admin=False) -> User`; `get_user_by_id(conn, user_id) -> User | None`; `get_user_by_username(conn, username) -> User | None`; `list_users(conn) -> list[User]`; `set_user_active(conn, user_id, active: bool) -> None`; `set_user_password(conn, user_id, new_password: str) -> None`. Routers and `deps.py` (Tasks 6-10) depend on these exact names.

- [ ] **Step 1: Write shared test fixtures**

```python
# tests/conftest.py
import pytest

from app.database import get_connection, init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = get_connection(path)
    init_db(conn)
    conn.close()
    return path


@pytest.fixture
def db(db_path):
    conn = get_connection(db_path)
    yield conn
    conn.close()


@pytest.fixture
def make_user(db):
    from app.users import create_user

    def _make(username, password="password123", display_name=None, is_admin=False):
        return create_user(
            db, username, password, display_name or username.title(), is_admin=is_admin
        )

    return _make
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_users.py
import sqlite3

import pytest

from app.users import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    set_user_active,
    set_user_password,
)
from app.security import verify_password


def test_create_user_hashes_password(db):
    user = create_user(db, "kid1", "hunter2", "Kid One")
    assert user.username == "kid1"
    assert user.display_name == "Kid One"
    assert user.is_admin is False
    assert user.active is True
    assert verify_password("hunter2", user.password_hash)


def test_create_user_defaults_to_non_admin_and_can_be_admin(db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assert kid.is_admin is False
    assert admin.is_admin is True


def test_create_user_rejects_duplicate_username(db):
    create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(sqlite3.IntegrityError):
        create_user(db, "kid1", "pw2", "Kid One Again")


def test_get_user_by_id_roundtrip(db):
    created = create_user(db, "kid1", "pw", "Kid One")
    fetched = get_user_by_id(db, created.id)
    assert fetched == created


def test_get_user_by_id_missing_returns_none(db):
    assert get_user_by_id(db, 999) is None


def test_get_user_by_username_missing_returns_none(db):
    assert get_user_by_username(db, "nobody") is None


def test_list_users_returns_all(db):
    create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "kid2", "pw", "Kid Two")
    usernames = {u.username for u in list_users(db)}
    assert usernames == {"kid1", "kid2"}


def test_set_user_active_deactivates(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    set_user_active(db, user.id, False)
    assert get_user_by_id(db, user.id).active is False


def test_set_user_password_updates_hash(db):
    user = create_user(db, "kid1", "oldpw", "Kid One")
    set_user_password(db, user.id, "newpw")
    updated = get_user_by_id(db, user.id)
    assert verify_password("newpw", updated.password_hash)
    assert not verify_password("oldpw", updated.password_hash)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_users.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.users'`

- [ ] **Step 4: Write the implementation**

```python
# app/users.py
import sqlite3
from dataclasses import dataclass
from typing import Optional

from app.security import hash_password


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    display_name: str
    is_admin: bool
    active: bool


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
        active=bool(row["active"]),
    )


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    display_name: str,
    is_admin: bool = False,
) -> User:
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) "
        "VALUES (?, ?, ?, ?)",
        (username, hash_password(password), display_name, int(is_admin)),
    )
    conn.commit()
    return get_user_by_id(conn, cur.lastrowid)


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[User]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[User]:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _row_to_user(row) if row else None


def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute("SELECT * FROM users ORDER BY display_name").fetchall()
    return [_row_to_user(row) for row in rows]


def set_user_active(conn: sqlite3.Connection, user_id: int, active: bool) -> None:
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
    conn.commit()


def set_user_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_users.py -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add app/users.py tests/test_users.py tests/conftest.py
git commit -m "feat: users data access layer"
```

---

### Task 5: Assignments data access

**Files:**
- Create: `app/assignments.py`
- Test: `tests/test_assignments.py`

**Interfaces:**
- Consumes: `db` and `make_user` fixtures (Task 4).
- Produces: `VALID_STATUSES = ("not_started", "in_progress", "done")`; `Assignment` dataclass (`id: int, user_id: int, subject: str, title: str, due_date: str, status: str`); `create_assignment(conn, user_id, subject, title, due_date, status="not_started") -> Assignment`; `get_assignment_by_id(conn, assignment_id) -> Assignment | None`; `list_assignments_for_user(conn, user_id) -> list[Assignment]`; `list_all_assignments(conn) -> list[Assignment]`; `update_assignment(conn, assignment_id, subject, title, due_date, status) -> None`; `delete_assignment(conn, assignment_id) -> None`. Routers (Tasks 8-9) depend on these exact names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assignments.py
import pytest

from app.assignments import (
    VALID_STATUSES,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    list_assignments_for_user,
    update_assignment,
)


def test_create_assignment_defaults_to_not_started(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Ch. 4 worksheet", "2026-09-25")
    assert assignment.status == "not_started"
    assert assignment.user_id == kid.id


def test_create_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    with pytest.raises(ValueError):
        create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="graded")


def test_get_assignment_by_id_roundtrip(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert get_assignment_by_id(db, created.id) == created


def test_get_assignment_by_id_missing_returns_none(db):
    assert get_assignment_by_id(db, 999) is None


def test_list_assignments_for_user_only_returns_that_user(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Lab report", "2026-09-26")

    kid1_assignments = list_assignments_for_user(db, kid1.id)
    assert len(kid1_assignments) == 1
    assert kid1_assignments[0].subject == "Math"


def test_list_assignments_for_user_sorted_by_due_date(db, make_user):
    kid = make_user("kid1")
    create_assignment(db, kid.id, "Math", "Later", "2026-10-01")
    create_assignment(db, kid.id, "Math", "Sooner", "2026-09-20")
    titles = [a.title for a in list_assignments_for_user(db, kid.id)]
    assert titles == ["Sooner", "Later"]


def test_list_all_assignments_spans_users(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Lab report", "2026-09-26")
    assert len(list_all_assignments(db)) == 2


def test_update_assignment_changes_fields(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done")
    assert get_assignment_by_id(db, created.id).status == "done"


def test_update_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    with pytest.raises(ValueError):
        update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "graded")


def test_delete_assignment_removes_it(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    delete_assignment(db, created.id)
    assert get_assignment_by_id(db, created.id) is None


def test_valid_statuses_constant():
    assert VALID_STATUSES == ("not_started", "in_progress", "done")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assignments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.assignments'`

- [ ] **Step 3: Write the implementation**

```python
# app/assignments.py
import sqlite3
from dataclasses import dataclass
from typing import Optional

VALID_STATUSES = ("not_started", "in_progress", "done")


@dataclass
class Assignment:
    id: int
    user_id: int
    subject: str
    title: str
    due_date: str
    status: str


def _row_to_assignment(row: sqlite3.Row) -> Assignment:
    return Assignment(
        id=row["id"],
        user_id=row["user_id"],
        subject=row["subject"],
        title=row["title"],
        due_date=row["due_date"],
        status=row["status"],
    )


def create_assignment(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    title: str,
    due_date: str,
    status: str = "not_started",
) -> Assignment:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    cur = conn.execute(
        "INSERT INTO assignments (user_id, subject, title, due_date, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, subject, title, due_date, status),
    )
    conn.commit()
    return get_assignment_by_id(conn, cur.lastrowid)


def get_assignment_by_id(conn: sqlite3.Connection, assignment_id: int) -> Optional[Assignment]:
    row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    return _row_to_assignment(row) if row else None


def list_assignments_for_user(conn: sqlite3.Connection, user_id: int) -> list[Assignment]:
    rows = conn.execute(
        "SELECT * FROM assignments WHERE user_id = ? ORDER BY due_date", (user_id,)
    ).fetchall()
    return [_row_to_assignment(row) for row in rows]


def list_all_assignments(conn: sqlite3.Connection) -> list[Assignment]:
    rows = conn.execute("SELECT * FROM assignments ORDER BY due_date").fetchall()
    return [_row_to_assignment(row) for row in rows]


def update_assignment(
    conn: sqlite3.Connection,
    assignment_id: int,
    subject: str,
    title: str,
    due_date: str,
    status: str,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    conn.execute(
        "UPDATE assignments SET subject = ?, title = ?, due_date = ?, status = ? WHERE id = ?",
        (subject, title, due_date, status, assignment_id),
    )
    conn.commit()


def delete_assignment(conn: sqlite3.Connection, assignment_id: int) -> None:
    conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assignments.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add app/assignments.py tests/test_assignments.py
git commit -m "feat: assignments data access layer"
```

---

### Task 6: Auth dependencies (session, current user, permission gates)

**Files:**
- Create: `app/deps.py`
- Test: `tests/test_deps.py`

**Interfaces:**
- Consumes: `get_connection` (Task 2), `User` / `get_user_by_id` (Task 4).
- Produces: `get_db(request: Request) -> Generator[sqlite3.Connection, None, None]`; `get_current_user(request, db) -> User | None`; `require_user(user=Depends(get_current_user)) -> User` (raises `HTTPException(303, headers={"Location": "/login"})` if not logged in, or if the logged-in user is inactive); `require_admin(user=Depends(require_user)) -> User` (raises `HTTPException(403)` if not admin). Every router (Tasks 7-10) depends on these exact names and behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deps.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.deps'`

- [ ] **Step 3: Write the implementation**

```python
# app/deps.py
import sqlite3
from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request

from app.database import get_connection
from app.users import User, get_user_by_id


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    request: Request, db: sqlite3.Connection = Depends(get_db)
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = get_user_by_id(db, user_id)
    if user is None or not user.active:
        return None
    return user


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_deps.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deps.py tests/test_deps.py
git commit -m "feat: session auth and permission dependencies"
```

---

### Task 7: App factory, base template, login/logout routes

**Files:**
- Create: `app/main.py`
- Create: `app/asgi.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/static/style.css`
- Create: `app/routers/auth.py`
- Test: `tests/test_auth_routes.py`
- Modify: `tests/conftest.py` (add `client` fixture)

**Interfaces:**
- Consumes: `get_db` (Task 6), `get_user_by_username` (Task 4), `verify_password` (Task 3).
- Produces: `create_app() -> FastAPI` in `app/main.py` (no import-time side effects — reads env vars only when called); `app = create_app()` in `app/asgi.py` (the uvicorn entrypoint). Routes: `GET /login`, `POST /login`, `POST /logout`, `GET /`. Tasks 8-11 register their routers onto the app built by `create_app()`.

- [ ] **Step 1: Add the `client` fixture**

```python
# tests/conftest.py  (add to the existing file)
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db_path, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-secret")
    from app.main import create_app

    app = create_app()
    return TestClient(app, follow_redirects=False)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_auth_routes.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_auth_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Write `app/database.py`-adjacent app wiring**

```python
# app/main.py
import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_connection, init_db
from app.routers import admin, admin_users, auth, overview


def create_app() -> FastAPI:
    app = FastAPI(title="Homework Manager")

    app.state.db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")

    secret_key = os.environ.get("SESSION_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SESSION_SECRET_KEY environment variable must be set")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    conn = get_connection(app.state.db_path)
    init_db(conn)
    conn.close()

    app.mount_static = None  # placeholder removed below once StaticFiles is wired (Step 4b)

    app.include_router(auth.router)
    app.include_router(overview.router)
    app.include_router(admin.router)
    app.include_router(admin_users.router)

    return app
```

- [ ] **Step 4b: Wire static files (replace the placeholder line above)**

Replace the `app.mount_static = None` line with:

```python
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
```

- [ ] **Step 5: Write `app/asgi.py`**

```python
# app/asgi.py
from app.main import create_app

app = create_app()
```

- [ ] **Step 6: Write `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Homework Manager{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <a class="brand" href="/">Homework Manager</a>
        {% if user %}
            <span class="who">{{ user.display_name }}</span>
            {% if user.is_admin %}
                <a href="/admin">All assignments</a>
                <a href="/admin/users">Manage users</a>
            {% else %}
                <a href="/overview">My assignments</a>
            {% endif %}
            <form method="post" action="/logout" class="inline">
                <button type="submit">Log out</button>
            </form>
        {% endif %}
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 7: Write `app/templates/login.html`**

```html
{% extends "base.html" %}
{% block title %}Log in — Homework Manager{% endblock %}
{% block content %}
<h1>Log in</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/login">
    <label>Username <input type="text" name="username" required autofocus></label>
    <label>Password <input type="password" name="password" required></label>
    <button type="submit">Log in</button>
</form>
{% endblock %}
```

- [ ] **Step 8: Write `app/static/style.css`**

```css
body { font-family: system-ui, sans-serif; margin: 0; background: #f7f7f9; color: #1a1a1a; }
nav { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1.5rem; background: #22314a; color: white; }
nav a, nav .who { color: white; text-decoration: none; }
nav .brand { font-weight: bold; margin-right: auto; }
nav form.inline { display: inline; margin: 0; }
nav button { background: none; border: 1px solid white; color: white; padding: 0.25rem 0.6rem; border-radius: 4px; cursor: pointer; }
main { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #ddd; }
form.stack label { display: block; margin-bottom: 0.5rem; }
.error { color: #b00020; }
.status-done { color: #1a7f37; font-weight: bold; }
.status-in_progress { color: #9a6700; }
.status-not_started { color: #57606a; }
```

- [ ] **Step 9: Write `app/routers/auth.py`**

```python
# app/routers/auth.py
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import get_current_user, get_db
from app.security import verify_password
from app.users import User, get_user_by_username

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=RedirectResponse)
def root(user: Optional[User] = Depends(get_current_user)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/admin" if user.is_admin else "/overview", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "login.html", {"request": request, "user": None, "error": error}
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: sqlite3.Connection = Depends(get_db),
):
    user = get_user_by_username(db, username)
    if user is None or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "user": None, "error": "Invalid username or password"},
            status_code=401,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/admin" if user.is_admin else "/overview", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 10: Create empty placeholder routers so `app/main.py` imports succeed**

Create `app/routers/overview.py`, `app/routers/admin.py`, `app/routers/admin_users.py`, each containing only:

```python
from fastapi import APIRouter

router = APIRouter()
```

(These get replaced with real routes in Tasks 8-10.)

- [ ] **Step 11: Run test to verify it passes**

Run: `pytest tests/test_auth_routes.py -v`
Expected: PASS (7 tests). Note: `test_logout_clears_session` will fail at the last assertion until Task 8 adds a real `/overview` route — for now, temporarily relax that one assertion to `assert protected.status_code in (303, 404)` and revisit it in Task 8's test run.

- [ ] **Step 12: Commit**

```bash
git add app/main.py app/asgi.py app/templates app/static app/routers/auth.py app/routers/overview.py app/routers/admin.py app/routers/admin_users.py tests/test_auth_routes.py tests/conftest.py
git commit -m "feat: app factory, base template, login/logout routes"
```

---

### Task 8: Kid overview page (own assignments)

**Files:**
- Modify: `app/routers/overview.py`
- Create: `app/templates/overview.html`
- Test: `tests/test_overview_routes.py`
- Modify: `tests/test_auth_routes.py:test_logout_clears_session` (restore the strict assertion now that `/overview` is real)

**Interfaces:**
- Consumes: `require_user`, `get_db` (Task 6); `create_assignment`, `list_assignments_for_user`, `get_assignment_by_id`, `update_assignment`, `delete_assignment`, `VALID_STATUSES` (Task 5).
- Produces: `GET /overview`, `POST /overview/add`, `POST /overview/{assignment_id}/status`, `POST /overview/{assignment_id}/delete` — all scoped to the logged-in user's own assignments; touching another user's assignment ID returns 403.

- [ ] **Step 1: Restore the strict assertion in Task 7's test**

```python
# tests/test_auth_routes.py — change the last two lines of test_logout_clears_session to:
    protected = client.get("/overview")
    assert protected.status_code == 303
    assert protected.headers["location"] == "/login"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_overview_routes.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_overview_routes.py -v`
Expected: FAIL — `/overview` returns 404 (placeholder router has no routes yet)

- [ ] **Step 4: Write the implementation**

```python
# app/routers/overview.py
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.assignments import (
    VALID_STATUSES,
    Assignment,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_assignments_for_user,
    update_assignment,
)
from app.deps import get_db, require_user
from app.users import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/overview", response_class=HTMLResponse)
def overview(
    request: Request,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    assignments = list_assignments_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "statuses": VALID_STATUSES,
        },
    )


@router.post("/overview/add")
def add_assignment(
    subject: str = Form(...),
    title: str = Form(...),
    due_date: str = Form(...),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    create_assignment(db, user.id, subject, title, due_date)
    return RedirectResponse("/overview", status_code=303)


def _own_assignment_or_403(
    db: sqlite3.Connection, assignment_id: int, user: User
) -> Assignment:
    assignment = get_assignment_by_id(db, assignment_id)
    if assignment is None or assignment.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your assignment")
    return assignment


@router.post("/overview/{assignment_id}/status")
def set_status(
    assignment_id: int,
    status: str = Form(...),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = _own_assignment_or_403(db, assignment_id, user)
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    update_assignment(
        db, assignment.id, assignment.subject, assignment.title, assignment.due_date, status
    )
    return RedirectResponse("/overview", status_code=303)


@router.post("/overview/{assignment_id}/delete")
def delete_own(
    assignment_id: int,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    _own_assignment_or_403(db, assignment_id, user)
    delete_assignment(db, assignment_id)
    return RedirectResponse("/overview", status_code=303)
```

- [ ] **Step 5: Write `app/templates/overview.html`**

```html
{% extends "base.html" %}
{% block title %}My Assignments — Homework Manager{% endblock %}
{% block content %}
<h1>My assignments</h1>

<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Status</th><th></th></tr>
    </thead>
    <tbody>
        {% for a in assignments %}
        <tr>
            <td>{{ a.subject }}</td>
            <td>{{ a.title }}</td>
            <td>{{ a.due_date }}</td>
            <td class="status-{{ a.status }}">
                <form method="post" action="/overview/{{ a.id }}/status" class="inline">
                    <select name="status" onchange="this.form.submit()">
                        {% for s in statuses %}
                        <option value="{{ s }}" {% if s == a.status %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
                        {% endfor %}
                    </select>
                </form>
            </td>
            <td>
                <form method="post" action="/overview/{{ a.id }}/delete" class="inline">
                    <button type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="5">Nothing due — you're all caught up.</td></tr>
        {% endfor %}
    </tbody>
</table>

<h2>Add an assignment</h2>
<form method="post" action="/overview/add" class="stack">
    <label>Subject <input type="text" name="subject" required></label>
    <label>Title <input type="text" name="title" required></label>
    <label>Due date <input type="date" name="due_date" required></label>
    <button type="submit">Add</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_overview_routes.py tests/test_auth_routes.py -v`
Expected: PASS (all tests, including the restored `test_logout_clears_session`)

- [ ] **Step 7: Commit**

```bash
git add app/routers/overview.py app/templates/overview.html tests/test_overview_routes.py tests/test_auth_routes.py
git commit -m "feat: kid overview page with own-assignment CRUD"
```

---

### Task 9: Admin assignments dashboard

**Files:**
- Modify: `app/routers/admin.py`
- Create: `app/templates/admin.html`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `require_admin`, `get_db` (Task 6); `list_all_assignments`, `get_assignment_by_id`, `update_assignment`, `delete_assignment`, `VALID_STATUSES` (Task 5); `list_users` (Task 4).
- Produces: `GET /admin` (optional `kid_id`, `status` query filters), `POST /admin/{assignment_id}/status`, `POST /admin/{assignment_id}/delete` — all admin-only, operate on any user's assignment.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_routes.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_routes.py -v`
Expected: FAIL — `/admin` returns 404 (placeholder router has no routes yet)

- [ ] **Step 3: Write the implementation**

```python
# app/routers/admin.py
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.assignments import (
    VALID_STATUSES,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    update_assignment,
)
from app.deps import get_db, require_admin
from app.users import User, list_users

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    kid_id: Optional[int] = None,
    status: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignments = list_all_assignments(db)
    if kid_id is not None:
        assignments = [a for a in assignments if a.user_id == kid_id]
    if status is not None:
        assignments = [a for a in assignments if a.status == status]

    users_by_id = {u.id: u for u in list_users(db)}

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "assignments": assignments,
            "users_by_id": users_by_id,
            "kids": [u for u in users_by_id.values() if not u.is_admin],
            "statuses": VALID_STATUSES,
            "selected_kid_id": kid_id,
            "selected_status": status,
        },
    )


@router.post("/admin/{assignment_id}/status")
def admin_set_status(
    assignment_id: int,
    status: str = Form(...),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = get_assignment_by_id(db, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Not found")
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    update_assignment(
        db, assignment.id, assignment.subject, assignment.title, assignment.due_date, status
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/{assignment_id}/delete")
def admin_delete(
    assignment_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = get_assignment_by_id(db, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_assignment(db, assignment_id)
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Step 4: Write `app/templates/admin.html`**

```html
{% extends "base.html" %}
{% block title %}All Assignments — Homework Manager{% endblock %}
{% block content %}
<h1>All assignments</h1>

<form method="get" action="/admin" class="stack">
    <label>Kid
        <select name="kid_id" onchange="this.form.submit()">
            <option value="">All kids</option>
            {% for kid in kids %}
            <option value="{{ kid.id }}" {% if selected_kid_id == kid.id %}selected{% endif %}>{{ kid.display_name }}</option>
            {% endfor %}
        </select>
    </label>
    <label>Status
        <select name="status" onchange="this.form.submit()">
            <option value="">All statuses</option>
            {% for s in statuses %}
            <option value="{{ s }}" {% if selected_status == s %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
            {% endfor %}
        </select>
    </label>
</form>

<table>
    <thead>
        <tr><th>Kid</th><th>Subject</th><th>Title</th><th>Due</th><th>Status</th><th></th></tr>
    </thead>
    <tbody>
        {% for a in assignments %}
        <tr>
            <td>{{ users_by_id[a.user_id].display_name }}</td>
            <td>{{ a.subject }}</td>
            <td>{{ a.title }}</td>
            <td>{{ a.due_date }}</td>
            <td class="status-{{ a.status }}">
                <form method="post" action="/admin/{{ a.id }}/status" class="inline">
                    <select name="status" onchange="this.form.submit()">
                        {% for s in statuses %}
                        <option value="{{ s }}" {% if s == a.status %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
                        {% endfor %}
                    </select>
                </form>
            </td>
            <td>
                <form method="post" action="/admin/{{ a.id }}/delete" class="inline">
                    <button type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="6">No assignments logged yet.</td></tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_admin_routes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/admin.py app/templates/admin.html tests/test_admin_routes.py
git commit -m "feat: admin dashboard across all kids' assignments"
```

---

### Task 10: Admin user management

**Files:**
- Modify: `app/routers/admin_users.py`
- Create: `app/templates/admin_users.html`
- Test: `tests/test_admin_users_routes.py`

**Interfaces:**
- Consumes: `require_admin`, `get_db` (Task 6); `create_user`, `get_user_by_id`, `get_user_by_username`, `list_users`, `set_user_active`, `set_user_password` (Task 4).
- Produces: `GET /admin/users`, `POST /admin/users/add`, `POST /admin/users/{user_id}/reset-password`, `POST /admin/users/{user_id}/deactivate`, `POST /admin/users/{user_id}/activate` — all admin-only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_users_routes.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_users_routes.py -v`
Expected: FAIL — `/admin/users` returns 404 (placeholder router has no routes yet)

- [ ] **Step 3: Write the implementation**

```python
# app/routers/admin_users.py
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import get_db, require_admin
from app.users import (
    User,
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    set_user_active,
    set_user_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin/users", response_class=HTMLResponse)
def manage_users(
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    return templates.TemplateResponse(
        "admin_users.html", {"request": request, "user": admin, "users": list_users(db)}
    )


@router.post("/admin/users/add")
def add_user(
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    is_admin: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    create_user(db, username, password, display_name, is_admin=is_admin is not None)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    new_password: str = Form(...),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_user_by_id(db, user_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    set_user_password(db, user_id, new_password)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_user_by_id(db, user_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    set_user_active(db, user_id, False)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/activate")
def activate_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_user_by_id(db, user_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    set_user_active(db, user_id, True)
    return RedirectResponse("/admin/users", status_code=303)
```

- [ ] **Step 4: Write `app/templates/admin_users.html`**

```html
{% extends "base.html" %}
{% block title %}Manage Users — Homework Manager{% endblock %}
{% block content %}
<h1>Manage users</h1>

<table>
    <thead>
        <tr><th>Name</th><th>Username</th><th>Admin</th><th>Active</th><th>Reset password</th><th></th></tr>
    </thead>
    <tbody>
        {% for u in users %}
        <tr>
            <td>{{ u.display_name }}</td>
            <td>{{ u.username }}</td>
            <td>{{ "Yes" if u.is_admin else "No" }}</td>
            <td>{{ "Yes" if u.active else "No" }}</td>
            <td>
                <form method="post" action="/admin/users/{{ u.id }}/reset-password" class="inline">
                    <input type="password" name="new_password" placeholder="New password" required minlength="6">
                    <button type="submit">Reset</button>
                </form>
            </td>
            <td>
                {% if u.active %}
                <form method="post" action="/admin/users/{{ u.id }}/deactivate" class="inline">
                    <button type="submit">Deactivate</button>
                </form>
                {% else %}
                <form method="post" action="/admin/users/{{ u.id }}/activate" class="inline">
                    <button type="submit">Activate</button>
                </form>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>

<h2>Add a user</h2>
<form method="post" action="/admin/users/add" class="stack">
    <label>Display name <input type="text" name="display_name" required></label>
    <label>Username <input type="text" name="username" required></label>
    <label>Password <input type="password" name="password" required minlength="6"></label>
    <label><input type="checkbox" name="is_admin"> Admin</label>
    <button type="submit">Add user</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_admin_users_routes.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/admin_users.py app/templates/admin_users.html tests/test_admin_users_routes.py
git commit -m "feat: admin user management (add, reset password, activate/deactivate)"
```

---

### Task 11: First-admin bootstrap script

**Files:**
- Create: `scripts/bootstrap_admin.py`
- Create: `scripts/__init__.py`
- Test: `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `get_connection`, `init_db` (Task 2); `create_user`, `get_user_by_username` (Task 4).
- Produces: `bootstrap_admin() -> None` — reads `HOMEWORK_DB_PATH`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME` from the environment; creates one admin user if `ADMIN_USERNAME` doesn't already exist; no-ops (does not error, does not duplicate) if it does. Used by `Dockerfile`'s container entrypoint (Task 12).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap.py
from app.users import get_user_by_username
from scripts.bootstrap_admin import bootstrap_admin


def test_bootstrap_creates_admin_when_none_exists(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_USERNAME", "parent1")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Parent One")

    bootstrap_admin()

    admin = get_user_by_username(db, "parent1")
    assert admin is not None
    assert admin.is_admin is True
    assert admin.display_name == "Parent One"


def test_bootstrap_is_idempotent(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_USERNAME", "parent1")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Parent One")

    bootstrap_admin()
    bootstrap_admin()  # must not raise or create a duplicate

    from app.users import list_users

    matching = [u for u in list_users(db) if u.username == "parent1"]
    assert len(matching) == 1


def test_bootstrap_skips_when_env_vars_missing(db_path, db, monkeypatch, capsys):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    bootstrap_admin()

    from app.users import list_users

    assert list_users(db) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bootstrap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/__init__.py
```

```python
# scripts/bootstrap_admin.py
import os

from app.database import get_connection, init_db
from app.users import create_user, get_user_by_username


def bootstrap_admin() -> None:
    db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME") or username or "Admin"

    if not username or not password:
        print("ADMIN_USERNAME and ADMIN_PASSWORD not set; skipping admin bootstrap.")
        return

    conn = get_connection(db_path)
    init_db(conn)
    try:
        if get_user_by_username(conn, username) is not None:
            print(f"Admin user '{username}' already exists; skipping.")
            return
        create_user(conn, username, password, display_name, is_admin=True)
        print(f"Created admin user '{username}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    bootstrap_admin()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bootstrap.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/bootstrap_admin.py tests/test_bootstrap.py
git commit -m "feat: first-admin bootstrap script"
```

---

### Task 12: Docker packaging and first run

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `README.md`

**Interfaces:**
- Consumes: `app/asgi.py:app` (Task 7), `scripts/bootstrap_admin.py:bootstrap_admin` (Task 11).
- Produces: a running container reachable at `http://localhost:8000`, with `/data/homework.db` on a named volume that survives `docker compose down`.

- [ ] **Step 1: Write the `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/

ENV HOMEWORK_DB_PATH=/data/homework.db

VOLUME ["/data"]

EXPOSE 8000

CMD ["sh", "-c", "python scripts/bootstrap_admin.py && uvicorn app.asgi:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  homework-manager:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - homework-data:/data
    environment:
      SESSION_SECRET_KEY: ${SESSION_SECRET_KEY}
      ADMIN_USERNAME: ${ADMIN_USERNAME}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      ADMIN_DISPLAY_NAME: ${ADMIN_DISPLAY_NAME:-Admin}
    restart: unless-stopped

volumes:
  homework-data:
```

- [ ] **Step 3: Write `.env.example`**

```
SESSION_SECRET_KEY=replace-with-a-long-random-string
ADMIN_USERNAME=parent1
ADMIN_PASSWORD=replace-with-a-real-password
ADMIN_DISPLAY_NAME=Mom
```

- [ ] **Step 4: Write `README.md`**

```markdown
# Homework Manager

Self-hosted homework tracker. Each kid logs their own assignments under
their own login; any account flagged admin (e.g. both parents) can see and
manage every kid's assignments and manage user accounts.

## First run

1. Copy `.env.example` to `.env` and fill in real values:
   ```bash
   cp .env.example .env
   ```
   - `SESSION_SECRET_KEY`: any long random string (e.g. `openssl rand -hex 32`).
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_DISPLAY_NAME`: the first
     admin account, created automatically on first startup. Once the app is
     running, use "Manage users" to add everyone else (kids and any other
     admins) — the bootstrap step only ever creates this one account.

2. Build and start the container:
   ```bash
   docker compose up --build
   ```

3. Open `http://localhost:8000`, log in with the admin account from step 1,
   and add the kids (and any other admins) under "Manage users".

Data lives in the `homework-data` Docker volume (`/data/homework.db` inside
the container) and survives `docker compose down` — only `docker compose
down -v` removes it.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```
```

- [ ] **Step 5: Run the full test suite one more time before packaging**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 2-11)

- [ ] **Step 6: Build and run the container**

```bash
cp .env.example .env
# edit .env with a real SESSION_SECRET_KEY and admin credentials
docker compose up --build -d
```

- [ ] **Step 7: Verify the container is serving and the admin account works**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login
```

Expected: `200`

Then open `http://localhost:8000/login` in a browser, log in with the
`ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env`, and confirm the admin
dashboard loads and "Manage users" lets you add a kid account.

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml .env.example README.md
git commit -m "feat: Docker packaging and first-run instructions"
```

---

## Self-Review Notes

- **Spec coverage:** admin-as-flag (Task 4), kid-scoped assignments with server-side 403 enforcement (Task 8, explicitly tested), admin cross-kid dashboard with filters (Task 9), admin user management (Task 10), generic invalid-login message (Task 7), SQLite on a mounted volume (Task 12), `HOMEWORK_DB_PATH`/`SESSION_SECRET_KEY` env-driven config (Tasks 6-7, 12), first-admin bootstrap solving the chicken-and-egg problem (Task 11) — every spec section maps to a task.
- **Reverse-proxy readiness:** the app never references its own origin/host directly (no hardcoded `http://localhost` anywhere in `app/`), so it needs no code change to sit behind a reverse proxy later — only a compose/network change, which is out of scope for this plan.
- **Type/name consistency:** checked `User`/`Assignment` field names and function signatures are used identically across Tasks 4-11 (e.g. `is_admin`, `active`, `VALID_STATUSES`, `user_id`).
