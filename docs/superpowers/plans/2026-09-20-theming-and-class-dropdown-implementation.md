# Per-Kid Theming and Class Dropdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-kid theme/accent-color customization and a per-kid class dropdown for the assignment "subject" field, to the already-deployed Homework Manager app.

**Architecture:** Two additive features on the existing FastAPI/SQLite app. Theming adds two columns to `users` plus a `/settings` route. Classes add a new `classes` table, an `/admin/classes` management section, and wire the existing assignment add/edit forms (kid overview + admin) to read that kid's active classes and render a dropdown instead of free text when any exist.

**Tech Stack:** Same as the existing app — Python/FastAPI, Jinja2, stdlib `sqlite3`, pytest + httpx `TestClient`. No new dependencies.

## Global Constraints

- `theme` ∈ `("light", "dark", "fun", "minimal")`, default `light`. `accent_color` ∈ `("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")`, default `blue`. Invalid values rejected server-side with 400, never silently stored.
- A user can only ever change their **own** theme/accent — `/settings` takes no ID, it always acts on `require_user`'s own row.
- The live SQLite database on the HomeLab deployment already has a `users` table **without** `theme`/`accent_color` columns. The migration must add them via `ALTER TABLE` on an existing table, guarded to run at most once (checking `PRAGMA table_info` first), and must not break a **fresh** install where `CREATE TABLE` already includes the new columns.
- `classes.user_id` always refers to a kid; `name` is required, `teacher`/`period`/`expires_on` are all optional (nullable).
- A class is **active** when `expires_on IS NULL OR expires_on >= today`. The boundary date itself (`expires_on == today`) counts as active.
- Subject dropdown shows only the class **name** (never teacher) per the approved design.
- When a kid has **zero** active classes, the subject field stays free text (today's behavior) — this is the confirmed fallback, not an error state.
- When a kid has one or more active classes, a submitted `subject` must exactly match one of those active class names, or the form re-renders with a 400 and an inline error (same "don't lose entered data" pattern already used for missing-field validation in `app/routers/overview.py` and `app/routers/admin.py`).
- `/admin/classes*` routes are admin-only (`require_admin`), consistent with every other `/admin*` route in the app.

---

## File Structure

```
app/
  theming.py              # NEW — VALID_THEMES, VALID_ACCENTS constants
  classes.py               # NEW — Class dataclass + data access
  database.py              # MODIFY — classes table, users theme/accent columns, migration
  users.py                 # MODIFY — User dataclass gains theme/accent_color, set_user_theme()
  routers/
    settings.py            # NEW — GET/POST /settings
    admin_classes.py        # NEW — /admin/classes* routes
    overview.py             # MODIFY — subject dropdown wiring on add/edit
    admin.py                # MODIFY — subject dropdown wiring on admin edit
  templates/
    base.html               # MODIFY — data-theme/data-accent on <body>, nav links
    settings.html            # NEW
    admin_classes.html        # NEW
    admin_class_edit.html      # NEW
    overview.html             # MODIFY — subject field becomes conditional
    overview_edit.html         # MODIFY — same
    admin_edit.html            # MODIFY — same
  static/
    style.css                 # MODIFY — CSS variables per theme/accent
  main.py                     # MODIFY — register settings + admin_classes routers
scripts/
  seed_classes.py               # NEW — idempotent seed for Elliott/Zander/Elizabeth's classes
tests/
  test_database.py               # MODIFY — migration tests
  test_users.py                   # MODIFY — theme/accent tests
  test_classes.py                  # NEW
  test_settings_routes.py           # NEW
  test_admin_classes_routes.py       # NEW
  test_overview_routes.py             # MODIFY — dropdown wiring tests
  test_admin_routes.py                 # MODIFY — dropdown wiring tests
  test_seed_classes.py                  # NEW
```

---

### Task 1: Database migration — classes table + users theme/accent columns

**Files:**
- Modify: `app/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces: `init_db(conn)` (existing function, behavior extended) now also creates a `classes` table (`id, user_id, name, teacher, period, expires_on, created_at`) and guarantees `users` has `theme TEXT NOT NULL DEFAULT 'light'` and `accent_color TEXT NOT NULL DEFAULT 'blue'`, whether starting from a fresh database or the existing live schema that predates this change. Every later task depends on these exact column names.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_database.py — add these to the existing file
def test_init_db_creates_classes_table(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "classes" in tables
    conn.close()


def test_init_db_migrates_existing_users_table_missing_theme_columns(tmp_path):
    db_path = tmp_path / "old.db"
    conn = get_connection(db_path)
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
        ("kid1", "hash", "Kid One"),
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "theme" in columns
    assert "accent_color" in columns
    row = conn.execute(
        "SELECT theme, accent_color FROM users WHERE username = 'kid1'"
    ).fetchone()
    assert row["theme"] == "light"
    assert row["accent_color"] == "blue"
    conn.close()


def test_init_db_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "new.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise "duplicate column name"
    conn.close()


def test_fresh_install_users_table_already_has_theme_columns(tmp_path):
    db_path = tmp_path / "fresh.db"
    conn = get_connection(db_path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "theme" in columns
    assert "accent_color" in columns
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py -v`
Expected: FAIL — `classes` table doesn't exist, `theme`/`accent_color` columns don't exist on a manually-created old-style `users` table

- [ ] **Step 3: Update `app/database.py`**

```python
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
    theme TEXT NOT NULL DEFAULT 'light',
    accent_color TEXT NOT NULL DEFAULT 'blue',
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

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    teacher TEXT,
    period INTEGER,
    expires_on TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_users_theme_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "theme" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'")
    if "accent_color" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN accent_color TEXT NOT NULL DEFAULT 'blue'")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate_users_theme_columns(conn)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: PASS (all tests, including the 3 pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: classes table and users theme/accent migration"
```

---

### Task 2: Users theme/accent data layer

**Files:**
- Create: `app/theming.py`
- Modify: `app/users.py`
- Test: `tests/test_users.py`

**Interfaces:**
- Consumes: `init_db` migration from Task 1 (so `theme`/`accent_color` columns exist).
- Produces: `VALID_THEMES = ("light", "dark", "fun", "minimal")`, `VALID_ACCENTS = ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")` in `app/theming.py`. `User` dataclass gains `theme: str` and `accent_color: str` fields (in this order, appended after `active`). `set_user_theme(conn, user_id, theme, accent_color) -> None`, raises `ValueError` for an invalid theme or accent. Routers in Tasks 4 depend on these exact names.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_users.py — add these to the existing file
from app.theming import VALID_ACCENTS, VALID_THEMES
from app.users import set_user_theme


def test_new_user_gets_default_theme_and_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    assert user.theme == "light"
    assert user.accent_color == "blue"


def test_set_user_theme_updates_theme_and_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    set_user_theme(db, user.id, "dark", "teal")
    updated = get_user_by_id(db, user.id)
    assert updated.theme == "dark"
    assert updated.accent_color == "teal"


def test_set_user_theme_rejects_invalid_theme(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(ValueError):
        set_user_theme(db, user.id, "neon", "blue")


def test_set_user_theme_rejects_invalid_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(ValueError):
        set_user_theme(db, user.id, "light", "chartreuse")


def test_valid_themes_and_accents_constants():
    assert VALID_THEMES == ("light", "dark", "fun", "minimal")
    assert VALID_ACCENTS == ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_users.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.theming'`

- [ ] **Step 3: Write `app/theming.py`**

```python
VALID_THEMES = ("light", "dark", "fun", "minimal")
VALID_ACCENTS = ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")
```

- [ ] **Step 4: Update `app/users.py`**

```python
import sqlite3
from dataclasses import dataclass
from typing import Optional

from app.security import hash_password
from app.theming import VALID_ACCENTS, VALID_THEMES


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    display_name: str
    is_admin: bool
    active: bool
    theme: str
    accent_color: str


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
        active=bool(row["active"]),
        theme=row["theme"],
        accent_color=row["accent_color"],
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


def set_user_theme(
    conn: sqlite3.Connection, user_id: int, theme: str, accent_color: str
) -> None:
    if theme not in VALID_THEMES:
        raise ValueError(f"invalid theme: {theme}")
    if accent_color not in VALID_ACCENTS:
        raise ValueError(f"invalid accent_color: {accent_color}")
    conn.execute(
        "UPDATE users SET theme = ?, accent_color = ? WHERE id = ?",
        (theme, accent_color, user_id),
    )
    conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_users.py -v`
Expected: PASS (all tests, including the 9 pre-existing ones — note `pytest` is already imported at the top of this file from the existing duplicate-username test)

- [ ] **Step 6: Commit**

```bash
git add app/theming.py app/users.py tests/test_users.py
git commit -m "feat: per-user theme and accent color"
```

---

### Task 3: Classes data access layer

**Files:**
- Create: `app/classes.py`
- Test: `tests/test_classes.py`

**Interfaces:**
- Consumes: `db` and `make_user` fixtures (from `tests/conftest.py`, Task 4 of the original plan — already exist).
- Produces: `Class` dataclass (`id: int, user_id: int, name: str, teacher: Optional[str], period: Optional[int], expires_on: Optional[str]`); `create_class(conn, user_id, name, teacher=None, period=None, expires_on=None) -> Class`; `get_class_by_id(conn, class_id) -> Class | None`; `list_classes_for_user(conn, user_id) -> list[Class]` (all classes, ordered by period then name); `list_active_classes_for_user(conn, user_id, today=None) -> list[Class]` (only non-expired, same ordering, `today` defaults to `date.today()` when `None` — the parameter exists so tests can pin a fixed date); `update_class(conn, class_id, name, teacher, period, expires_on) -> None`; `delete_class(conn, class_id) -> None`. Routers in Tasks 5-7 depend on these exact names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classes.py
from datetime import date

from app.classes import (
    create_class,
    delete_class,
    get_class_by_id,
    list_active_classes_for_user,
    list_classes_for_user,
    update_class,
)


def test_create_class_with_all_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Science", teacher="Rogers", period=2, expires_on="2026-12-31")
    assert c.name == "Science"
    assert c.teacher == "Rogers"
    assert c.period == 2
    assert c.expires_on == "2026-12-31"


def test_create_class_with_minimal_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "A+ Tutoring")
    assert c.teacher is None
    assert c.period is None
    assert c.expires_on is None


def test_get_class_by_id_missing_returns_none(db):
    assert get_class_by_id(db, 999) is None


def test_list_classes_for_user_orders_by_period_then_name(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Third", period=3)
    create_class(db, kid.id, "First", period=1)
    create_class(db, kid.id, "NoPeriod")
    names = [c.name for c in list_classes_for_user(db, kid.id)]
    assert names == ["First", "Third", "NoPeriod"]


def test_list_classes_for_user_only_that_users_classes(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_class(db, kid1.id, "Math")
    create_class(db, kid2.id, "Science")
    names = [c.name for c in list_classes_for_user(db, kid1.id)]
    assert names == ["Math"]


def test_list_active_classes_excludes_expired(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Expired", expires_on="2026-01-01")
    create_class(db, kid.id, "Active", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 9, 20))
    assert [c.name for c in active] == ["Active"]


def test_list_active_classes_includes_never_expiring(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Forever", expires_on=None)
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 9, 20))
    assert [c.name for c in active] == ["Forever"]


def test_list_active_classes_boundary_inclusive_on_expiry_date(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "LastDay", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 12, 31))
    assert [c.name for c in active] == ["LastDay"]


def test_list_active_classes_excludes_day_after_expiry(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Expired", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2027, 1, 1))
    assert active == []


def test_update_class_changes_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Math", period=1)
    update_class(db, c.id, "Advanced Math", "Smith", 2, "2026-12-31")
    updated = get_class_by_id(db, c.id)
    assert updated.name == "Advanced Math"
    assert updated.teacher == "Smith"
    assert updated.period == 2
    assert updated.expires_on == "2026-12-31"


def test_delete_class_removes_it(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Math")
    delete_class(db, c.id)
    assert get_class_by_id(db, c.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_classes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.classes'`

- [ ] **Step 3: Write the implementation**

```python
# app/classes.py
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Class:
    id: int
    user_id: int
    name: str
    teacher: Optional[str]
    period: Optional[int]
    expires_on: Optional[str]


def _row_to_class(row: sqlite3.Row) -> Class:
    return Class(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        teacher=row["teacher"],
        period=row["period"],
        expires_on=row["expires_on"],
    )


def create_class(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    teacher: Optional[str] = None,
    period: Optional[int] = None,
    expires_on: Optional[str] = None,
) -> Class:
    cur = conn.execute(
        "INSERT INTO classes (user_id, name, teacher, period, expires_on) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, teacher, period, expires_on),
    )
    conn.commit()
    return get_class_by_id(conn, cur.lastrowid)


def get_class_by_id(conn: sqlite3.Connection, class_id: int) -> Optional[Class]:
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    return _row_to_class(row) if row else None


def list_classes_for_user(conn: sqlite3.Connection, user_id: int) -> list[Class]:
    rows = conn.execute(
        "SELECT * FROM classes WHERE user_id = ? ORDER BY period IS NULL, period, name",
        (user_id,),
    ).fetchall()
    return [_row_to_class(row) for row in rows]


def list_active_classes_for_user(
    conn: sqlite3.Connection, user_id: int, today: Optional[date] = None
) -> list[Class]:
    today_str = (today or date.today()).isoformat()
    rows = conn.execute(
        "SELECT * FROM classes WHERE user_id = ? "
        "AND (expires_on IS NULL OR expires_on >= ?) "
        "ORDER BY period IS NULL, period, name",
        (user_id, today_str),
    ).fetchall()
    return [_row_to_class(row) for row in rows]


def update_class(
    conn: sqlite3.Connection,
    class_id: int,
    name: str,
    teacher: Optional[str],
    period: Optional[int],
    expires_on: Optional[str],
) -> None:
    conn.execute(
        "UPDATE classes SET name = ?, teacher = ?, period = ?, expires_on = ? WHERE id = ?",
        (name, teacher, period, expires_on, class_id),
    )
    conn.commit()


def delete_class(conn: sqlite3.Connection, class_id: int) -> None:
    conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_classes.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add app/classes.py tests/test_classes.py
git commit -m "feat: classes data access layer"
```

---

### Task 4: Settings page, theme CSS, and base template wiring

**Files:**
- Create: `app/routers/settings.py`
- Create: `app/templates/settings.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/style.css` (full replace)
- Modify: `app/main.py`
- Test: `tests/test_settings_routes.py`

**Interfaces:**
- Consumes: `require_user`, `get_db` (from `app/deps.py`); `VALID_THEMES`, `VALID_ACCENTS` (Task 2); `set_user_theme` (Task 2).
- Produces: `GET /settings`, `POST /settings` — any logged-in user manages their own `theme`/`accent_color`. Registers into `create_app()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_routes.py
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
    assert 'value="light" selected' in resp.text


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_routes.py -v`
Expected: FAIL — `/settings` returns 404 (route doesn't exist yet)

- [ ] **Step 3: Write `app/routers/settings.py`**

```python
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import get_db, require_user
from app.theming import VALID_ACCENTS, VALID_THEMES
from app.users import User, set_user_theme

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings", response_class=HTMLResponse)
def settings_form(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "themes": VALID_THEMES,
            "accents": VALID_ACCENTS,
        },
    )


@router.post("/settings")
def settings_submit(
    request: Request,
    theme: str = Form(...),
    accent_color: str = Form(...),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    if theme not in VALID_THEMES or accent_color not in VALID_ACCENTS:
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "user": user,
                "themes": VALID_THEMES,
                "accents": VALID_ACCENTS,
                "error": "Invalid theme or accent color.",
            },
            status_code=400,
        )
    set_user_theme(db, user.id, theme, accent_color)
    return RedirectResponse("/settings", status_code=303)
```

- [ ] **Step 4: Write `app/templates/settings.html`**

```html
{% extends "base.html" %}
{% block title %}Settings — Homework Manager{% endblock %}
{% block content %}
<h1>My settings</h1>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/settings" class="stack">
    <label>Theme
        <select name="theme">
            {% for t in themes %}
            <option value="{{ t }}" {% if t == user.theme %}selected{% endif %}>{{ t.title() }}</option>
            {% endfor %}
        </select>
    </label>
    <label>Accent color
        <select name="accent_color">
            {% for a in accents %}
            <option value="{{ a }}" {% if a == user.accent_color %}selected{% endif %}>{{ a.title() }}</option>
            {% endfor %}
        </select>
    </label>
    <button type="submit">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Update `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Homework Manager{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body data-theme="{{ user.theme if user else 'light' }}" data-accent="{{ user.accent_color if user else 'blue' }}">
    <nav>
        <a class="brand" href="/">Homework Manager</a>
        {% if user %}
            <span class="who">{{ user.display_name }}</span>
            {% if user.is_admin %}
                <a href="/admin">All assignments</a>
                <a href="/admin/users">Manage users</a>
                <a href="/admin/classes">Manage classes</a>
            {% else %}
                <a href="/overview">My assignments</a>
            {% endif %}
            <a href="/settings">Settings</a>
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

- [ ] **Step 6: Replace `app/static/style.css` in full**

```css
:root {
    --accent: #3a7bd5;
    --bg: #f7f7f9;
    --text: #1a1a1a;
    --card-bg: #ffffff;
    --border: #ddd;
    --radius: 4px;
}

body[data-theme="dark"] {
    --bg: #14161f;
    --text: #e8e8ec;
    --card-bg: #1c1e29;
    --border: #2a2d3a;
}

body[data-theme="fun"] {
    --bg: #fff3e9;
    --card-bg: #ffffff;
    --border: #f0d9c0;
    --radius: 14px;
}

body[data-theme="minimal"] {
    --bg: #ffffff;
    --card-bg: #ffffff;
    --border: #1a1a1a;
    --radius: 0;
}

body[data-accent="red"] { --accent: #d64545; }
body[data-accent="orange"] { --accent: #e08a2e; }
body[data-accent="yellow"] { --accent: #d6b32e; }
body[data-accent="green"] { --accent: #4a9d4f; }
body[data-accent="teal"] { --accent: #2e9d8f; }
body[data-accent="blue"] { --accent: #3a7bd5; }
body[data-accent="purple"] { --accent: #7b4fd6; }
body[data-accent="pink"] { --accent: #d6469b; }

body { font-family: system-ui, sans-serif; margin: 0; background: var(--bg); color: var(--text); }
nav { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1.5rem; background: var(--accent); color: white; }
nav a, nav .who { color: white; text-decoration: none; }
nav .brand { font-weight: bold; margin-right: auto; }
nav form.inline { display: inline; margin: 0; }
nav button { background: none; border: 1px solid white; color: white; padding: 0.25rem 0.6rem; border-radius: 4px; cursor: pointer; }
main { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
table { width: 100%; border-collapse: collapse; margin-top: 1rem; background: var(--card-bg); }
th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
form.stack label { display: block; margin-bottom: 0.5rem; }
.error { color: #b00020; }
.status-done { color: #1a7f37; font-weight: bold; }
.status-in_progress { color: #9a6700; }
.status-not_started { color: #57606a; }
button, select, input { border-radius: var(--radius); }
```

- [ ] **Step 7: Register the router in `app/main.py`**

```python
# app/main.py
import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_connection, init_db
from app.routers import admin, admin_users, auth, overview, settings


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

    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(auth.router)
    app.include_router(overview.router)
    app.include_router(admin.router)
    app.include_router(admin_users.router)
    app.include_router(settings.router)

    return app
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_settings_routes.py -v`
Expected: PASS (5 tests)

Run: `pytest -v`
Expected: PASS (full suite — confirms the CSS/base.html/main.py changes didn't break any existing route test)

- [ ] **Step 9: Commit**

```bash
git add app/routers/settings.py app/templates/settings.html app/templates/base.html app/static/style.css app/main.py tests/test_settings_routes.py
git commit -m "feat: per-kid theme and accent color settings page"
```

---

### Task 5: Admin classes management

**Files:**
- Create: `app/routers/admin_classes.py`
- Create: `app/templates/admin_classes.html`
- Create: `app/templates/admin_class_edit.html`
- Modify: `app/main.py`
- Test: `tests/test_admin_classes_routes.py`

**Interfaces:**
- Consumes: `require_admin`, `get_db` (from `app/deps.py`); `create_class`, `get_class_by_id`, `list_classes_for_user`, `update_class`, `delete_class` (Task 3); `list_users` (existing, `app/users.py`).
- Produces: `GET /admin/classes`, `POST /admin/classes/add`, `GET /admin/classes/{class_id}/edit`, `POST /admin/classes/{class_id}/edit`, `POST /admin/classes/{class_id}/delete` — all admin-only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_classes_routes.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_classes_routes.py -v`
Expected: FAIL — `/admin/classes` returns 404 (route doesn't exist yet)

- [ ] **Step 3: Write `app/routers/admin_classes.py`**

```python
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.classes import (
    create_class,
    delete_class,
    get_class_by_id,
    list_classes_for_user,
    update_class,
)
from app.deps import get_db, require_admin
from app.users import User, list_users

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_period(period: Optional[str]) -> Optional[int]:
    if not period or not period.strip():
        return None
    try:
        return int(period)
    except ValueError:
        return None


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    return value.strip()


@router.get("/admin/classes", response_class=HTMLResponse)
def manage_classes(
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    kids = [u for u in list_users(db) if not u.is_admin]
    classes_by_kid = {kid.id: list_classes_for_user(db, kid.id) for kid in kids}
    return templates.TemplateResponse(
        "admin_classes.html",
        {
            "request": request,
            "user": admin,
            "kids": kids,
            "classes_by_kid": classes_by_kid,
        },
    )


@router.post("/admin/classes/add")
def add_class(
    user_id: int = Form(...),
    name: str = Form(...),
    teacher: Optional[str] = Form(None),
    period: Optional[str] = Form(None),
    expires_on: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    create_class(
        db,
        user_id,
        name,
        teacher=_clean_optional(teacher),
        period=_parse_period(period),
        expires_on=_clean_optional(expires_on),
    )
    return RedirectResponse("/admin/classes", status_code=303)


@router.get("/admin/classes/{class_id}/edit", response_class=HTMLResponse)
def edit_class_form(
    class_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    cls = get_class_by_id(db, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse(
        "admin_class_edit.html", {"request": request, "user": admin, "cls": cls}
    )


@router.post("/admin/classes/{class_id}/edit")
def edit_class(
    class_id: int,
    name: str = Form(...),
    teacher: Optional[str] = Form(None),
    period: Optional[str] = Form(None),
    expires_on: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_class_by_id(db, class_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    update_class(
        db,
        class_id,
        name,
        _clean_optional(teacher),
        _parse_period(period),
        _clean_optional(expires_on),
    )
    return RedirectResponse("/admin/classes", status_code=303)


@router.post("/admin/classes/{class_id}/delete")
def delete_class_route(
    class_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    if get_class_by_id(db, class_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_class(db, class_id)
    return RedirectResponse("/admin/classes", status_code=303)
```

- [ ] **Step 4: Write `app/templates/admin_classes.html`**

```html
{% extends "base.html" %}
{% block title %}Manage Classes — Homework Manager{% endblock %}
{% block content %}
<h1>Manage classes</h1>

{% for kid in kids %}
<h2>{{ kid.display_name }}</h2>
<table>
    <thead>
        <tr><th>Period</th><th>Class</th><th>Teacher</th><th>Expires</th><th></th><th></th></tr>
    </thead>
    <tbody>
        {% for c in classes_by_kid[kid.id] %}
        <tr>
            <td>{{ c.period if c.period is not none else '' }}</td>
            <td>{{ c.name }}</td>
            <td>{{ c.teacher or '' }}</td>
            <td>{{ c.expires_on or 'never' }}</td>
            <td><a href="/admin/classes/{{ c.id }}/edit">Edit</a></td>
            <td>
                <form method="post" action="/admin/classes/{{ c.id }}/delete" class="inline">
                    <button type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="6">No classes yet.</td></tr>
        {% endfor %}
    </tbody>
</table>
{% endfor %}
{% if not kids %}
<p>No kids yet — add one under <a href="/admin/users">Manage users</a> first.</p>
{% endif %}

{% if kids %}
<h2>Add a class</h2>
<form method="post" action="/admin/classes/add" class="stack">
    <label>Kid
        <select name="user_id" required>
            {% for kid in kids %}
            <option value="{{ kid.id }}">{{ kid.display_name }}</option>
            {% endfor %}
        </select>
    </label>
    <label>Period <input type="number" name="period"></label>
    <label>Class name <input type="text" name="name" required></label>
    <label>Teacher <input type="text" name="teacher"></label>
    <label>Expires on <input type="date" name="expires_on"></label>
    <button type="submit">Add class</button>
</form>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Write `app/templates/admin_class_edit.html`**

```html
{% extends "base.html" %}
{% block title %}Edit Class — Homework Manager{% endblock %}
{% block content %}
<h1>Edit class</h1>
<form method="post" action="/admin/classes/{{ cls.id }}/edit" class="stack">
    <label>Period <input type="number" name="period" value="{{ cls.period if cls.period is not none else '' }}"></label>
    <label>Class name <input type="text" name="name" value="{{ cls.name }}" required></label>
    <label>Teacher <input type="text" name="teacher" value="{{ cls.teacher or '' }}"></label>
    <label>Expires on <input type="date" name="expires_on" value="{{ cls.expires_on or '' }}"></label>
    <button type="submit">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Register the router in `app/main.py`**

```python
# app/main.py — update the import and include_router lines
from app.routers import admin, admin_classes, admin_users, auth, overview, settings

# ...inside create_app(), alongside the other include_router calls:
    app.include_router(admin_classes.router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_admin_classes_routes.py -v`
Expected: PASS (9 tests)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 8: Commit**

```bash
git add app/routers/admin_classes.py app/templates/admin_classes.html app/templates/admin_class_edit.html app/main.py tests/test_admin_classes_routes.py
git commit -m "feat: admin class management for each kid"
```

---

### Task 6: Kid subject dropdown (overview add/edit)

**Files:**
- Modify: `app/routers/overview.py`
- Modify: `app/templates/overview.html`
- Modify: `app/templates/overview_edit.html`
- Test: `tests/test_overview_routes.py`

**Interfaces:**
- Consumes: `list_active_classes_for_user` (Task 3).
- Produces: `/overview` (GET) and its add/edit forms now pass `active_classes` to their templates and reject (400) a submitted `subject` that isn't one of the kid's active class names, whenever the kid has at least one active class.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overview_routes.py — add these to the existing file
from app.classes import create_class


def test_add_assignment_shows_dropdown_when_active_classes_exist(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert '<select name="subject"' in resp.text


def test_add_assignment_shows_free_text_when_no_active_classes(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'type="text" name="subject"' in resp.text


def test_add_assignment_accepts_subject_from_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.post(
        "/overview/add", data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25"}
    )
    assert resp.status_code == 303


def test_add_assignment_rejects_subject_not_in_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    _login(client, "kid1")
    resp = client.post(
        "/overview/add", data={"subject": "Gym", "title": "Worksheet", "due_date": "2026-09-25"}
    )
    assert resp.status_code == 400
    from app.assignments import list_assignments_for_user

    assert list_assignments_for_user(db, kid.id) == []


def test_add_assignment_allows_free_text_when_no_active_classes(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add",
        data={"subject": "Anything", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 303


def test_edit_page_shows_dropdown_when_active_classes_exist(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.get(f"/overview/{assignment.id}/edit")
    assert '<select name="subject"' in resp.text


def test_edit_rejects_subject_not_in_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Gym", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assert resp.status_code == 400
```

Note: `tests/test_overview_routes.py` already starts with `from app.assignments import create_assignment` and `from app.users import create_user` (used by the existing tests) — both names are available at module level for the new tests above without adding imports. `list_assignments_for_user` is not imported at module level anywhere in this file (the one existing test that needs it imports it inline, as shown above) — follow that same inline-import convention, don't add a module-level import for it.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_overview_routes.py -v`
Expected: FAIL — no `active_classes` context var yet, dropdown never renders, invalid subjects aren't rejected

- [ ] **Step 3: Update `app/routers/overview.py`**

```python
import sqlite3
from typing import Optional

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
from app.classes import list_active_classes_for_user
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
    active_classes = list_active_classes_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "statuses": VALID_STATUSES,
            "active_classes": active_classes,
        },
    )


@router.post("/overview/add")
def add_assignment(
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    active_classes = list_active_classes_for_user(db, user.id)
    if not (subject and subject.strip()) or not (title and title.strip()) or not (
        due_date and due_date.strip()
    ):
        assignments = list_assignments_for_user(db, user.id)
        return templates.TemplateResponse(
            "overview.html",
            {
                "request": request,
                "user": user,
                "assignments": assignments,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "error": "Subject, title, and due date are all required.",
                "form_subject": subject or "",
                "form_title": title or "",
                "form_due_date": due_date or "",
            },
            status_code=400,
        )
    if active_classes and subject not in {c.name for c in active_classes}:
        assignments = list_assignments_for_user(db, user.id)
        return templates.TemplateResponse(
            "overview.html",
            {
                "request": request,
                "user": user,
                "assignments": assignments,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "error": "Please choose a subject from the list.",
                "form_subject": subject,
                "form_title": title,
                "form_due_date": due_date,
            },
            status_code=400,
        )
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


@router.get("/overview/{assignment_id}/edit", response_class=HTMLResponse)
def edit_assignment_form(
    assignment_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = _own_assignment_or_403(db, assignment_id, user)
    active_classes = list_active_classes_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview_edit.html",
        {
            "request": request,
            "user": user,
            "assignment": assignment,
            "active_classes": active_classes,
            "form_subject": assignment.subject,
            "form_title": assignment.title,
            "form_due_date": assignment.due_date,
        },
    )


@router.post("/overview/{assignment_id}/edit")
def edit_assignment(
    assignment_id: int,
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = _own_assignment_or_403(db, assignment_id, user)
    active_classes = list_active_classes_for_user(db, user.id)
    if not (subject and subject.strip()) or not (title and title.strip()) or not (
        due_date and due_date.strip()
    ):
        return templates.TemplateResponse(
            "overview_edit.html",
            {
                "request": request,
                "user": user,
                "assignment": assignment,
                "active_classes": active_classes,
                "error": "Subject, title, and due date are all required.",
                "form_subject": subject or "",
                "form_title": title or "",
                "form_due_date": due_date or "",
            },
            status_code=400,
        )
    if active_classes and subject not in {c.name for c in active_classes}:
        return templates.TemplateResponse(
            "overview_edit.html",
            {
                "request": request,
                "user": user,
                "assignment": assignment,
                "active_classes": active_classes,
                "error": "Please choose a subject from the list.",
                "form_subject": subject,
                "form_title": title,
                "form_due_date": due_date,
            },
            status_code=400,
        )
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status)
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

- [ ] **Step 4: Update the subject field in `app/templates/overview.html`**

Replace this line:

```html
    <label>Subject <input type="text" name="subject" value="{{ form_subject or '' }}" required></label>
```

with:

```html
    <label>Subject
        {% if active_classes %}
        <select name="subject" required>
            <option value="" disabled {% if not form_subject %}selected{% endif %}>Choose a class</option>
            {% for c in active_classes %}
            <option value="{{ c.name }}" {% if c.name == form_subject %}selected{% endif %}>{{ c.name }}</option>
            {% endfor %}
        </select>
        {% else %}
        <input type="text" name="subject" value="{{ form_subject or '' }}" required>
        {% endif %}
    </label>
```

- [ ] **Step 5: Update the subject field in `app/templates/overview_edit.html`** the same way

Replace:

```html
    <label>Subject <input type="text" name="subject" value="{{ form_subject or '' }}" required></label>
```

with the identical conditional block from Step 4.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_overview_routes.py -v`
Expected: PASS (all tests, including the 7 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 7: Commit**

```bash
git add app/routers/overview.py app/templates/overview.html app/templates/overview_edit.html tests/test_overview_routes.py
git commit -m "feat: subject dropdown from active classes on kid overview forms"
```

---

### Task 7: Admin subject dropdown (admin edit)

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `app/templates/admin_edit.html`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `list_active_classes_for_user` (Task 3).
- Produces: `/admin/{assignment_id}/edit` (GET and POST) now use the **owning kid's** (`assignment.user_id`, not the logged-in admin's) active classes for the dropdown and validation — same behavior as Task 6 but on the admin edit form.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_routes.py — add these to the existing file
from app.classes import create_class


def test_admin_edit_shows_dropdown_for_kid_with_active_classes(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.get(f"/admin/{assignment.id}/edit")
    assert '<select name="subject"' in resp.text


def test_admin_edit_rejects_subject_not_in_kids_active_class_list(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_class(db, kid.id, "Math", period=1)
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Gym",
            "title": "Worksheet",
            "due_date": "2026-09-25",
            "status": "not_started",
        },
    )
    assert resp.status_code == 400
```

Note: `tests/test_admin_routes.py` already starts with `from app.assignments import create_assignment, get_assignment_by_id` and `from app.users import create_user`, plus `import pytest` and the `_login` helper — all used by the existing tests. `create_assignment`, `create_user`, and `_login` are already available at module level for the new tests above; no new imports needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_routes.py -v`
Expected: FAIL — no dropdown rendered, invalid subject not rejected

- [ ] **Step 3: Update `app/routers/admin.py`**

```python
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
from app.classes import list_active_classes_for_user
from app.deps import get_db, require_admin
from app.users import User, list_users

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    kid_id: Optional[str] = None,
    status: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignments = list_all_assignments(db)

    try:
        kid_id_int = int(kid_id) if kid_id else None
    except ValueError:
        kid_id_int = None
    if kid_id_int is not None:
        assignments = [a for a in assignments if a.user_id == kid_id_int]

    status_filter = status if status else None
    if status_filter is not None:
        assignments = [a for a in assignments if a.status == status_filter]

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
            "selected_kid_id": kid_id_int,
            "selected_status": status_filter,
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


@router.get("/admin/{assignment_id}/edit", response_class=HTMLResponse)
def admin_edit_form(
    assignment_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = get_assignment_by_id(db, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Not found")
    active_classes = list_active_classes_for_user(db, assignment.user_id)
    return templates.TemplateResponse(
        "admin_edit.html",
        {
            "request": request,
            "user": admin,
            "assignment": assignment,
            "statuses": VALID_STATUSES,
            "active_classes": active_classes,
            "form_subject": assignment.subject,
            "form_title": assignment.title,
            "form_due_date": assignment.due_date,
            "form_status": assignment.status,
        },
    )


@router.post("/admin/{assignment_id}/edit")
def admin_edit(
    assignment_id: int,
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignment = get_assignment_by_id(db, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Not found")
    active_classes = list_active_classes_for_user(db, assignment.user_id)
    if not (subject and subject.strip()) or not (title and title.strip()) or not (
        due_date and due_date.strip()
    ):
        return templates.TemplateResponse(
            "admin_edit.html",
            {
                "request": request,
                "user": admin,
                "assignment": assignment,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "error": "Subject, title, and due date are all required.",
                "form_subject": subject or "",
                "form_title": title or "",
                "form_due_date": due_date or "",
                "form_status": status or assignment.status,
            },
            status_code=400,
        )
    if active_classes and subject not in {c.name for c in active_classes}:
        return templates.TemplateResponse(
            "admin_edit.html",
            {
                "request": request,
                "user": admin,
                "assignment": assignment,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "error": "Please choose a subject from the list.",
                "form_subject": subject,
                "form_title": title,
                "form_due_date": due_date,
                "form_status": status or assignment.status,
            },
            status_code=400,
        )
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    update_assignment(db, assignment.id, subject, title, due_date, status)
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

- [ ] **Step 4: Update the subject field in `app/templates/admin_edit.html`**

Replace this line:

```html
    <label>Subject <input type="text" name="subject" value="{{ form_subject or '' }}" required></label>
```

with:

```html
    <label>Subject
        {% if active_classes %}
        <select name="subject" required>
            <option value="" disabled {% if not form_subject %}selected{% endif %}>Choose a class</option>
            {% for c in active_classes %}
            <option value="{{ c.name }}" {% if c.name == form_subject %}selected{% endif %}>{{ c.name }}</option>
            {% endfor %}
        </select>
        {% else %}
        <input type="text" name="subject" value="{{ form_subject or '' }}" required>
        {% endif %}
    </label>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_admin_routes.py -v`
Expected: PASS (all tests, including the 2 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 6: Commit**

```bash
git add app/routers/admin.py app/templates/admin_edit.html tests/test_admin_routes.py
git commit -m "feat: subject dropdown from owning kid's active classes on admin edit"
```

---

### Task 8: Seed script for this semester's classes

**Files:**
- Create: `scripts/seed_classes.py`
- Test: `tests/test_seed_classes.py`

**Interfaces:**
- Consumes: `get_connection`, `init_db` (Task 1); `create_class`, `list_classes_for_user` (Task 3); `get_user_by_username` (existing, `app/users.py`).
- Produces: `seed_classes() -> None` — idempotent (safe to re-run: skips a class that already exists by name for that user, skips a username that has no `users` row yet with a printed message rather than erroring). Used by the deployment step in Task 9.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_classes.py
from app.classes import list_classes_for_user
from app.users import create_user, get_user_by_username
from scripts.seed_classes import seed_classes


def test_seed_classes_creates_classes_for_existing_user(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    names = {c.name for c in classes}
    assert "Ecology" in names
    assert "Marching Band" in names
    assert len(classes) == 7


def test_seed_classes_sets_expiration_on_every_class(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    assert all(c.expires_on == "2026-12-31" for c in classes)


def test_seed_classes_skips_missing_users(db_path, db, monkeypatch, capsys):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    seed_classes()
    captured = capsys.readouterr()
    assert "does not exist yet" in captured.out


def test_seed_classes_is_idempotent(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()
    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    assert len(classes) == 7


def test_seed_classes_seeds_elizabeths_full_list(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "eacain", "pw", "Elizabeth")

    seed_classes()

    elizabeth = get_user_by_username(db, "eacain")
    classes = list_classes_for_user(db, elizabeth.id)
    names = {c.name for c in classes}
    assert names == {
        "Jazz Band",
        "Science",
        "American History",
        "ELA",
        "Athletic Fitness",
        "Math",
        "Choir",
    }
    assert len(classes) == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_seed_classes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.seed_classes'`

- [ ] **Step 3: Write `scripts/seed_classes.py`**

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classes import create_class, list_classes_for_user
from app.database import get_connection, init_db
from app.users import get_user_by_username

SEMESTER_EXPIRES_ON = "2026-12-31"

CLASS_LISTS = {
    "ebcain": [
        (1, "Jazz Band", "Lamar"),
        (2, "Science", "Rogers"),
        (3, "American History", "McNeil"),
        (4, "PE", "Campos"),
        (5, "ELA", "Hutson"),
        (6, "Honors Algebra", "Seyer"),
        (7, "Challenge", "Taylor"),
    ],
    "zcain": [
        (1, "Ecology", "Morton"),
        (2, "Personal Finances", "Wamble"),
        (3, "Industrial Tech", "Hobeck"),
        (4, "Advanced Foods", "Newman"),
        (5, "A+ Tutoring", None),
        (6, "College Readiness", "Taylor"),
        (7, "Marching Band", "Lamar"),
    ],
    "eacain": [
        (1, "Jazz Band", "Lamar"),
        (2, "Science", "Dugas"),
        (3, "American History", None),
        (4, "ELA", None),
        (5, "Athletic Fitness", None),
        (6, "Math", "Campos"),
        (7, "Choir", None),
    ],
}


def seed_classes() -> None:
    db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")
    conn = get_connection(db_path)
    init_db(conn)
    try:
        for username, classes in CLASS_LISTS.items():
            user = get_user_by_username(conn, username)
            if user is None:
                print(f"User '{username}' does not exist yet; skipping their classes.")
                continue
            existing_names = {c.name for c in list_classes_for_user(conn, user.id)}
            for period, name, teacher in classes:
                if name in existing_names:
                    print(f"'{username}' already has '{name}'; skipping.")
                    continue
                create_class(
                    conn,
                    user.id,
                    name,
                    teacher=teacher,
                    period=period,
                    expires_on=SEMESTER_EXPIRES_ON,
                )
                print(f"Added '{name}' (period {period}) for '{username}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed_classes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_seed_classes.py -v`
Expected: PASS (5 tests)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_classes.py tests/test_seed_classes.py
git commit -m "feat: seed script for this semester's class lists"
```

---

### Task 9: Deployment

**Files:** none (operational task against the live HomeLab deployment — no code changes)

**Interfaces:**
- Consumes: everything from Tasks 1-8, already pushed to `master`.

This mirrors the original rollout (`A:\Project\homework-manager`, GitHub repo `MTNHMMR/homework-manager`, Portainer stack `homework-manager` on endpoint `local` at `192.168.1.235:9443`, live app at `http://192.168.1.235:8010`).

- [ ] **Step 1: Push to GitHub**

```bash
git push origin master
```

- [ ] **Step 2: Redeploy the Portainer stack**

```bash
curl -sk -X PUT "https://192.168.1.235:9443/api/stacks/7/git/redeploy?endpointId=3" \
  -H "X-API-Key: <the Portainer API token>" \
  -H "Content-Type: application/json" \
  -d '{"RepositoryReferenceName":"refs/heads/master","RepositoryAuthentication":false,"pullImage":true}'
```

- [ ] **Step 3: Verify the migration ran cleanly against the live database**

Confirm the existing accounts (`admindad`, `zcain`) can still log in after the redeploy — a broken migration would most likely surface as a 500 on login or on `/overview`/`/admin`, since `_row_to_user` now reads `theme`/`accent_color` columns that must exist on every row, including rows created before this change.

```bash
curl -sk -c /tmp/verify_cookies.txt -X POST "http://192.168.1.235:8010/login" \
  -d "username=admindad&password=<the current admin password>" \
  -w "\nHTTP:%{http_code}\n"
```

Expected: `303` redirecting to `/admin`, not a `500`.

- [ ] **Step 4: Confirm Elliott and Elizabeth's accounts exist**

Per the design spec, these were to be created via "Manage users" before their classes can be seeded (`ebcain`, `eacain`). If they don't exist yet as of this deployment, create them now through the same admin UI flow used for the original `zcain` account, then proceed.

- [ ] **Step 5: Run the seed script against the live container**

The container doesn't have an interactive shell exposed by default — run it via Portainer's exec API against the running `homework-manager` container (get the current container ID from `GET /api/endpoints/3/docker/containers/json?all=true`, filtering for the `homework-manager` image, since the container ID changes on every redeploy):

```bash
curl -sk -X POST "https://192.168.1.235:9443/api/endpoints/3/docker/containers/<container-id>/exec" \
  -H "X-API-Key: <the Portainer API token>" \
  -H "Content-Type: application/json" \
  -d '{"AttachStdout":true,"AttachStderr":true,"Cmd":["python","-m","scripts.seed_classes"]}'
```

then start the returned exec instance:

```bash
curl -sk -X POST "https://192.168.1.235:9443/api/endpoints/3/docker/exec/<exec-id>/start" \
  -H "X-API-Key: <the Portainer API token>" \
  -H "Content-Type: application/json" \
  -d '{"Detach":false,"Tty":false}'
```

Expected output: one "Added '<class>' ..." line per class across all three kids (21 total if Elizabeth's account already exists with only her 3 known classes, fewer if any account is still missing — matches `test_seed_classes_skips_missing_users`' documented behavior).

- [ ] **Step 6: Verify end-to-end in the browser or via curl**

- Log in as `zcain`, confirm `/overview`'s "Add an assignment" section now shows a `<select>` with Zander's 7 classes instead of a free-text subject field.
- On `/settings`, change theme to `dark` and accent to `teal`, save, and confirm the page re-renders with those values pre-selected (persisted, not just client-side).
- Log in as `admindad`, visit `/admin/classes`, and confirm all three kids' rosters display with the correct periods, teachers, and `2026-12-31` expiration.
