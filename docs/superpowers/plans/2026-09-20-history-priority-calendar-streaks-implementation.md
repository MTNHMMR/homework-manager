# Completed History, Priority Flag, Weekly View, and Streaks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four v6 features from `docs/superpowers/specs/2026-09-20-history-priority-calendar-streaks-design.md`: a completed-work history view, a priority ("important") flag on assignments, an alternate weekly calendar view, and on-time streak stats per kid.

**Architecture:** Two new columns on `assignments` (`priority`, `completed_at`) added via the same additive-migration pattern already used for `users.theme`/`users.accent_color`. `completed_at` is maintained by `update_assignment`/`create_assignment` whenever status becomes/stops being `done`. All four features are read-layer/UI additions on top of that: sorting and a visual marker for priority, two new read-only routes for history, a pure computation for streaks, and a query-param-toggled alternate rendering for the weekly view. No feature requires a background job or new dependency.

**Tech Stack:** Same as the existing app — Python/FastAPI, Jinja2, stdlib `sqlite3`/`datetime`, pytest + httpx `TestClient`. No new dependencies.

## Global Constraints

- `priority` is a single boolean flag ("important"), not a multi-level field.
- `completed_at` is set to `datetime('now')` the moment `status` becomes `'done'`, and cleared back to `NULL` the moment `status` changes away from `'done'`. It is left unchanged on a no-op update that keeps `status == 'done'`.
- Priority-flagged assignments sort before unflagged ones within whatever list/group they're already in; due-date order is preserved within each tier (stable sort over the already-`due_date`-ordered query result).
- The weekly view is a Sun–Sat column layout (`view=week`, `week=<ISO date of that week's Sunday>` query params), not a month grid, and sits alongside the existing flat list (`view=list` or no `view` param) via a toggle — it never replaces the existing table.
- A streak is an **on-time** streak: consecutive days, walking backward from yesterday, where every assignment due that day has `completed_at` set. A day with zero assignments due doesn't break or extend the streak. A streak of 0 renders nothing (no "🔥 0-day streak" clutter).
- History views (`/overview/history`, `/admin/history`) are read-mostly but each row keeps an **Edit** link (reusing the existing edit routes/forms) — the only way to undo a mistaken "done" once an assignment has fallen off the active list per v4.
- Ships to the same live deployment (Portainer stack `homework-manager`, `192.168.1.235:8010`) via push to `master` + Portainer git-redeploy, same as v3/v4.

---

## File Structure

```
app/
  database.py            # MODIFY (Task 1) — priority/completed_at columns + migration
  assignments.py          # MODIFY (Tasks 2, 3, 4, 5) — dataclass fields, create/update logic,
                           #   sort_by_priority, list_completed_assignments_for_user,
                           #   list_all_completed_assignments, compute_streak
  weeks.py                 # CREATE (Task 6) — pure week-grouping helpers, no DB access
  routers/
    overview.py             # MODIFY (Tasks 2, 3, 4, 5, 6)
    admin.py                  # MODIFY (Tasks 2, 3, 4, 5, 6)
  templates/
    base.html                  # MODIFY (Task 4) — History nav link
    overview.html                # MODIFY (Tasks 3, 5, 6) — priority checkbox/marker, streak, week toggle
    overview_edit.html           # MODIFY (Task 3) — priority checkbox
    admin.html                    # MODIFY (Tasks 3, 5, 6) — priority marker, streak, week toggle
    admin_edit.html                # MODIFY (Task 3) — priority checkbox
    overview_history.html          # CREATE (Task 4)
    admin_history.html              # CREATE (Task 4)
  static/
    style.css                        # MODIFY (Tasks 3, 5, 6) — priority mark, streak badge, week grid
tests/
  test_database.py         # MODIFY (Task 1)
  test_assignments.py       # MODIFY (Tasks 2, 3, 4, 5)
  test_overview_routes.py   # MODIFY (Tasks 2, 3, 4, 5, 6)
  test_admin_routes.py       # MODIFY (Tasks 2, 3, 4, 5, 6)
```

---

### Task 1: Database migration — `priority` and `completed_at` columns

**Files:**
- Modify: `app/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: nothing — foundation task.
- Produces: `assignments` table gains `priority INTEGER NOT NULL DEFAULT 0` and `completed_at TEXT` (nullable), on both fresh installs (baked into `SCHEMA`) and existing databases (via a new migration function, same pattern as `_migrate_users_theme_columns`). Task 2 depends on these columns existing.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_database.py — add these to the existing file
def test_init_db_migrates_existing_assignments_table_missing_priority_and_completed_columns(tmp_path):
    db_path = tmp_path / "old_assignments.db"
    conn = get_connection(db_path)
    conn.execute(
        """
        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO assignments (user_id, subject, title, due_date) VALUES (?, ?, ?, ?)",
        (1, "Math", "Worksheet", "2026-09-25"),
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
    assert "priority" in columns
    assert "completed_at" in columns
    row = conn.execute(
        "SELECT priority, completed_at FROM assignments WHERE subject = 'Math'"
    ).fetchone()
    assert row["priority"] == 0
    assert row["completed_at"] is None
    conn.close()


def test_init_db_assignments_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "new_assignments.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise "duplicate column name"
    conn.close()


def test_fresh_install_assignments_table_already_has_new_columns(tmp_path):
    db_path = tmp_path / "fresh_assignments.db"
    conn = get_connection(db_path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
    assert "priority" in columns
    assert "completed_at" in columns
    conn.close()
```

Note: `get_connection`, `init_db` are already imported at the top of `tests/test_database.py` — no new imports needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_database.py -v`
Expected: FAIL — `priority`/`completed_at` don't exist yet

- [ ] **Step 3: Replace `app/database.py` in full**

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
    priority INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
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


def _migrate_assignments_priority_and_completed_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()
    }
    if "priority" not in existing:
        conn.execute("ALTER TABLE assignments ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
    if "completed_at" not in existing:
        conn.execute("ALTER TABLE assignments ADD COLUMN completed_at TEXT")
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate_users_theme_columns(conn)
    _migrate_assignments_priority_and_completed_columns(conn)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_database.py -v`
Expected: PASS (all tests, including the 3 new ones)

Run: `pytest -v`
Expected: FAIL — `test_assignments.py`, `test_overview_routes.py`, `test_admin_routes.py` will now fail because `Assignment` rows fetched via `SELECT *` include the new columns but `_row_to_assignment` in `app/assignments.py` doesn't read them yet, and the dataclass doesn't declare them. This is expected and fixed in Task 2 — do not attempt to fix `app/assignments.py` in this task.

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: add priority and completed_at columns to assignments"
```

---

### Task 2: Assignment data layer — track `priority` and `completed_at`

**Files:**
- Modify: `app/assignments.py`
- Modify: `app/routers/overview.py:108-128` (only `set_status` and `edit_assignment`'s `update_assignment` call)
- Modify: `app/routers/admin.py:64-79,109-163` (only `admin_set_status` and `admin_edit`'s `update_assignment` call)
- Test: `tests/test_assignments.py`

**Interfaces:**
- Consumes: `priority`/`completed_at` columns from Task 1.
- Produces: `Assignment` dataclass gains `priority: bool` and `completed_at: Optional[str]` fields. `create_assignment(..., priority: bool = False)` — new optional kwarg, backward compatible with every existing call site. `update_assignment(..., priority: bool)` — **new required positional/keyword arg**, every existing caller (in this codebase and in tests) must be updated to pass one. This task does **not** add any UI for setting priority yet (that's Task 3) — every router call site in this task passes `assignment.priority` (i.e. "leave priority unchanged"), so end-user-visible behavior is identical to before this task; only the data layer and its direct tests change.

- [ ] **Step 1: Update the two existing `update_assignment` calls in `tests/test_assignments.py` to pass a priority argument**

In `tests/test_assignments.py`, change:

```python
def test_update_assignment_changes_fields(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done")
    assert get_assignment_by_id(db, created.id).status == "done"
```

to:

```python
def test_update_assignment_changes_fields(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).status == "done"
```

and change:

```python
def test_update_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    with pytest.raises(ValueError):
        update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "graded")
```

to:

```python
def test_update_assignment_rejects_invalid_status(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    with pytest.raises(ValueError):
        update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "graded", False)
```

- [ ] **Step 2: Write the new failing tests**

Append to `tests/test_assignments.py`:

```python
def test_create_assignment_defaults_priority_false(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert assignment.priority is False


def test_create_assignment_accepts_priority_true(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", priority=True)
    assert assignment.priority is True


def test_create_assignment_sets_completed_at_when_created_done(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    assert assignment.completed_at is not None


def test_create_assignment_leaves_completed_at_none_when_not_done(db, make_user):
    kid = make_user("kid1")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    assert assignment.completed_at is None


def test_update_assignment_sets_completed_at_when_marked_done(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).completed_at is not None


def test_update_assignment_clears_completed_at_when_changed_away_from_done(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "in_progress", False)
    assert get_assignment_by_id(db, created.id).completed_at is None


def test_update_assignment_keeps_completed_at_on_noop_done_update(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25", status="done")
    original_completed_at = get_assignment_by_id(db, created.id).completed_at
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "done", False)
    assert get_assignment_by_id(db, created.id).completed_at == original_completed_at


def test_update_assignment_persists_priority(db, make_user):
    kid = make_user("kid1")
    created = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    update_assignment(db, created.id, "Math", "Worksheet", "2026-09-25", "not_started", True)
    assert get_assignment_by_id(db, created.id).priority is True
```

Note: `create_assignment`, `get_assignment_by_id`, `update_assignment` are already imported at the top of `tests/test_assignments.py` — no new imports needed.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_assignments.py -v`
Expected: FAIL — `Assignment` has no `priority`/`completed_at` fields yet, `update_assignment` doesn't accept a 6th positional arg

- [ ] **Step 4: Replace `app/assignments.py` in full**

```python
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
    priority: bool
    completed_at: Optional[str]


def _row_to_assignment(row: sqlite3.Row) -> Assignment:
    return Assignment(
        id=row["id"],
        user_id=row["user_id"],
        subject=row["subject"],
        title=row["title"],
        due_date=row["due_date"],
        status=row["status"],
        priority=bool(row["priority"]),
        completed_at=row["completed_at"],
    )


def _now(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT datetime('now')").fetchone()[0]


def create_assignment(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    title: str,
    due_date: str,
    status: str = "not_started",
    priority: bool = False,
) -> Assignment:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    completed_at = _now(conn) if status == "done" else None
    cur = conn.execute(
        "INSERT INTO assignments (user_id, subject, title, due_date, status, priority, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, subject, title, due_date, status, int(priority), completed_at),
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
    priority: bool,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    current = get_assignment_by_id(conn, assignment_id)
    if status == "done" and current.status != "done":
        completed_at = _now(conn)
    elif status != "done":
        completed_at = None
    else:
        completed_at = current.completed_at
    conn.execute(
        "UPDATE assignments SET subject = ?, title = ?, due_date = ?, status = ?, "
        "priority = ?, completed_at = ? WHERE id = ?",
        (subject, title, due_date, status, int(priority), completed_at, assignment_id),
    )
    conn.commit()


def delete_assignment(conn: sqlite3.Connection, assignment_id: int) -> None:
    conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    conn.commit()
```

- [ ] **Step 5: Update the `update_assignment` call in `set_status` in `app/routers/overview.py`**

Replace:

```python
    update_assignment(
        db, assignment.id, assignment.subject, assignment.title, assignment.due_date, status
    )
```

with:

```python
    update_assignment(
        db,
        assignment.id,
        assignment.subject,
        assignment.title,
        assignment.due_date,
        status,
        assignment.priority,
    )
```

(This is the only change in `set_status`; everything else in the function is unchanged.)

- [ ] **Step 6: Update the `update_assignment` call in `edit_assignment`'s success path in `app/routers/overview.py`**

Replace:

```python
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status)
    return RedirectResponse("/overview", status_code=303)
```

with:

```python
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status, assignment.priority)
    return RedirectResponse("/overview", status_code=303)
```

(Nothing else in `edit_assignment` changes yet — the form still doesn't send a `priority` field, so `assignment.priority` — i.e. "unchanged" — is correct here until Task 3.)

- [ ] **Step 7: Update the `update_assignment` call in `admin_set_status` in `app/routers/admin.py`**

Replace:

```python
    update_assignment(
        db, assignment.id, assignment.subject, assignment.title, assignment.due_date, status
    )
```

with:

```python
    update_assignment(
        db,
        assignment.id,
        assignment.subject,
        assignment.title,
        assignment.due_date,
        status,
        assignment.priority,
    )
```

- [ ] **Step 8: Update the `update_assignment` call in `admin_edit`'s success path in `app/routers/admin.py`**

Replace:

```python
    update_assignment(db, assignment.id, subject, title, due_date, status)
    return RedirectResponse("/admin", status_code=303)
```

with:

```python
    update_assignment(db, assignment.id, subject, title, due_date, status, assignment.priority)
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_assignments.py -v`
Expected: PASS (all tests, including the 8 new ones)

Run: `pytest -v`
Expected: PASS (full suite — confirms the router call-site updates didn't break `test_overview_routes.py`/`test_admin_routes.py`, which don't pass `priority` themselves and don't need to yet)

- [ ] **Step 10: Commit**

```bash
git add app/assignments.py app/routers/overview.py app/routers/admin.py tests/test_assignments.py
git commit -m "feat: track priority and completed_at on assignments"
```

---

### Task 3: Priority flag UI — checkbox, marker, and sort

**Files:**
- Modify: `app/assignments.py` (append one function)
- Modify: `app/routers/overview.py`
- Modify: `app/routers/admin.py`
- Modify: `app/templates/overview.html`
- Modify: `app/templates/overview_edit.html`
- Modify: `app/templates/admin_edit.html`
- Modify: `app/templates/admin.html`
- Modify: `app/static/style.css`
- Test: `tests/test_overview_routes.py`, `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `Assignment.priority`, `update_assignment(..., priority: bool)`, `create_assignment(..., priority: bool = False)` from Task 2.
- Produces: `sort_by_priority(assignments: list[Assignment]) -> list[Assignment]` in `app/assignments.py`, used here and reused by Task 6's weekly view. Add/edit forms send a `priority` checkbox field (`"1"` when checked, absent when not). Row templates render a `<span class="priority-mark">` before a flagged assignment's title.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_routes.py` (first, change the top import line from `from app.assignments import create_assignment` to `from app.assignments import create_assignment, get_assignment_by_id, list_assignments_for_user` — `get_assignment_by_id` and `list_assignments_for_user` are new imports needed by the tests below):

```python
def test_add_assignment_with_priority_checked_persists_it(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.post(
        "/overview/add",
        data={"subject": "Math", "title": "Big Test", "due_date": "2026-09-25", "priority": "1"},
    )
    assert resp.status_code == 303
    assignments = list_assignments_for_user(db, kid.id)
    assert assignments[0].priority is True


def test_add_assignment_without_priority_defaults_false(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    client.post(
        "/overview/add",
        data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25"},
    )
    assignments = list_assignments_for_user(db, kid.id)
    assert assignments[0].priority is False


def test_overview_shows_priority_marker_for_flagged_assignment(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Big Test", "2026-09-25", priority=True)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="priority-mark"' in resp.text


def test_overview_sorts_priority_assignments_first(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Sooner Regular", "2026-09-20")
    create_assignment(db, kid.id, "Science", "Later Important", "2026-09-26", priority=True)
    _login(client, "kid1")
    resp = client.get("/overview")
    assert resp.text.index("Later Important") < resp.text.index("Sooner Regular")


def test_edit_assignment_can_toggle_priority(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.post(
        f"/overview/{assignment.id}/edit",
        data={"subject": "Math", "title": "Worksheet", "due_date": "2026-09-25", "priority": "1"},
    )
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id).priority is True
```

Append to `tests/test_admin_routes.py`:

```python
def test_admin_dashboard_shows_priority_marker(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Big Test", "2026-09-25", priority=True)
    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="priority-mark"' in resp.text


def test_admin_dashboard_sorts_priority_assignments_first_within_kid(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Sooner Regular", "2026-09-20")
    create_assignment(db, kid1.id, "Science", "Later Important", "2026-09-26", priority=True)
    _login(client, "parent1")
    resp = client.get("/admin")
    assert resp.text.index("Later Important") < resp.text.index("Sooner Regular")


def test_admin_edit_can_toggle_priority(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assignment = create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.post(
        f"/admin/{assignment.id}/edit",
        data={
            "subject": "Math",
            "title": "Worksheet",
            "due_date": "2026-09-25",
            "status": "not_started",
            "priority": "1",
        },
    )
    assert resp.status_code == 303
    assert get_assignment_by_id(db, assignment.id).priority is True
```

Note: `get_assignment_by_id` is already imported at the top of `tests/test_admin_routes.py` — no new import needed there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: FAIL — no priority checkbox, marker, or sort exists yet

- [ ] **Step 3: Append `sort_by_priority` to `app/assignments.py`**

Add this function at the end of `app/assignments.py`, after `delete_assignment`:

```python


def sort_by_priority(assignments: list[Assignment]) -> list[Assignment]:
    """Priority-flagged assignments first; stable sort preserves due-date order within each tier."""
    return sorted(assignments, key=lambda a: not a.priority)
```

- [ ] **Step 4: Update `app/routers/overview.py`**

Add `sort_by_priority` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    Assignment,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_assignments_for_user,
    sort_by_priority,
    update_assignment,
)
```

In `overview()`, replace:

```python
    assignments = _visible_assignments(list_assignments_for_user(db, user.id), today)
```

with:

```python
    assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
```

In `add_assignment()`, add a `priority` form field to the function signature:

```python
@router.post("/overview/add")
def add_assignment(
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
```

In the same function, replace both occurrences of:

```python
        assignments = _visible_assignments(list_assignments_for_user(db, user.id), today)
```

with:

```python
        assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
```

and add `"form_priority": bool(priority),` to both error-branch context dicts (each currently ends its dict with `"form_due_date": due_date or "",` or `"form_due_date": due_date,` right before the closing brace — add the new key on the line after that one in both places).

Replace the success line:

```python
    create_assignment(db, user.id, subject, title, due_date)
    return RedirectResponse("/overview", status_code=303)
```

with:

```python
    create_assignment(db, user.id, subject, title, due_date, priority=bool(priority))
    return RedirectResponse("/overview", status_code=303)
```

In `edit_assignment_form()`, add `"form_priority": assignment.priority,` to its context dict (alongside the existing `"form_subject"`/`"form_title"`/`"form_due_date"` keys).

In `edit_assignment()`, add a `priority` form field to the function signature (same as `add_assignment`'s), and add `"form_priority": bool(priority),` to both of its error-branch context dicts. Replace the success line:

```python
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status, assignment.priority)
    return RedirectResponse("/overview", status_code=303)
```

with:

```python
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status, bool(priority))
    return RedirectResponse("/overview", status_code=303)
```

- [ ] **Step 5: Update `app/routers/admin.py`**

Add `sort_by_priority` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    sort_by_priority,
    update_assignment,
)
```

In `admin_dashboard()`, replace:

```python
    assignments_by_kid_id: dict[int, list] = {}
    for a in assignments:
```

with:

```python
    assignments = sort_by_priority(assignments)

    assignments_by_kid_id: dict[int, list] = {}
    for a in assignments:
```

In `admin_edit_form()`, add `"form_priority": assignment.priority,` to its context dict (alongside `"form_status"`).

In `admin_edit()`, add a `priority` form field to the function signature:

```python
@router.post("/admin/{assignment_id}/edit")
def admin_edit(
    assignment_id: int,
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
```

Add `"form_priority": bool(priority),` to both of its error-branch context dicts (alongside `"form_status"`). Replace the success line:

```python
    update_assignment(db, assignment.id, subject, title, due_date, status, assignment.priority)
    return RedirectResponse("/admin", status_code=303)
```

with:

```python
    update_assignment(db, assignment.id, subject, title, due_date, status, bool(priority))
    return RedirectResponse("/admin", status_code=303)
```

- [ ] **Step 6: Add the priority checkbox and marker to `app/templates/overview.html`**

Replace:

```html
            <td>{{ a.subject }}</td>
            <td>{{ a.title }}</td>
```

with:

```html
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
```

Replace:

```html
    <label>Due date <input type="date" name="due_date" value="{{ form_due_date or '' }}" required></label>
    <button type="submit">Add</button>
```

with:

```html
    <label>Due date <input type="date" name="due_date" value="{{ form_due_date or '' }}" required></label>
    <label class="checkbox"><input type="checkbox" name="priority" value="1" {% if form_priority %}checked{% endif %}> Important</label>
    <button type="submit">Add</button>
```

- [ ] **Step 7: Add the priority checkbox to `app/templates/overview_edit.html`**

Replace:

```html
    <label>Due date <input type="date" name="due_date" value="{{ form_due_date or '' }}" required></label>
    <button type="submit">Save</button>
```

with:

```html
    <label>Due date <input type="date" name="due_date" value="{{ form_due_date or '' }}" required></label>
    <label class="checkbox"><input type="checkbox" name="priority" value="1" {% if form_priority %}checked{% endif %}> Important</label>
    <button type="submit">Save</button>
```

- [ ] **Step 8: Add the priority checkbox to `app/templates/admin_edit.html`**

Replace:

```html
    <label>Status
        <select name="status">
            {% for s in statuses %}
            <option value="{{ s }}" {% if s == form_status %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
            {% endfor %}
        </select>
    </label>
    <button type="submit">Save</button>
```

with:

```html
    <label>Status
        <select name="status">
            {% for s in statuses %}
            <option value="{{ s }}" {% if s == form_status %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
            {% endfor %}
        </select>
    </label>
    <label class="checkbox"><input type="checkbox" name="priority" value="1" {% if form_priority %}checked{% endif %}> Important</label>
    <button type="submit">Save</button>
```

- [ ] **Step 9: Add the priority marker to `app/templates/admin.html`**

Replace:

```html
            <td>{{ a.subject }}</td>
            <td>{{ a.title }}</td>
```

with:

```html
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
```

- [ ] **Step 10: Add CSS**

Add to `app/static/style.css`, anywhere after the existing rules (e.g. right after the `tr.overdue` rule):

```css
.priority-mark { color: var(--accent); }
label.checkbox { display: flex; align-items: center; gap: 0.4rem; }
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `pytest tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: PASS (all tests, including the 8 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 12: Commit**

```bash
git add app/assignments.py app/routers/overview.py app/routers/admin.py app/templates/overview.html app/templates/overview_edit.html app/templates/admin_edit.html app/templates/admin.html app/static/style.css tests/test_overview_routes.py tests/test_admin_routes.py
git commit -m "feat: add priority flag with checkbox, marker, and sort-to-top"
```

---

### Task 4: Completed-work history

**Files:**
- Modify: `app/assignments.py` (append two functions)
- Modify: `app/routers/overview.py`
- Modify: `app/routers/admin.py`
- Modify: `app/templates/base.html`
- Create: `app/templates/overview_history.html`
- Create: `app/templates/admin_history.html`
- Test: `tests/test_overview_routes.py`, `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `Assignment.completed_at` from Task 2.
- Produces: `list_completed_assignments_for_user(conn, user_id) -> list[Assignment]` and `list_all_completed_assignments(conn) -> list[Assignment]` in `app/assignments.py`, both `ORDER BY completed_at DESC`. New routes `GET /overview/history` and `GET /admin/history`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_overview_routes.py`:

```python
def test_overview_history_requires_login(client):
    resp = client.get("/overview/history")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_overview_history_shows_own_completed_assignments(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert resp.status_code == 200
    assert "Finished HW" in resp.text


def test_overview_history_excludes_not_done_assignments(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Still Working HW", "2026-09-25")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert "Still Working HW" not in resp.text


def test_overview_history_excludes_other_kids_completed_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    kid2 = create_user(db, "kid2", "pw", "Kid Two")
    create_assignment(db, kid2.id, "Math", "Other Kid HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert "Other Kid HW" not in resp.text


def test_overview_history_has_edit_link(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    assignment = create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview/history")
    assert f'/overview/{assignment.id}/edit' in resp.text
```

Append to `tests/test_admin_routes.py`:

```python
def test_admin_history_requires_admin(client, db):
    create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/admin/history")
    assert resp.status_code == 403


def test_admin_history_requires_login(client):
    resp = client.get("/admin/history")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_history_shows_all_kids_completed_assignments_grouped(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Finished", "2020-01-01", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Finished", "2020-01-02", status="done")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert resp.status_code == 200
    assert "Alice Finished" in resp.text
    assert "Bob Finished" in resp.text


def test_admin_history_excludes_not_done_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Still Working HW", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert "Still Working HW" not in resp.text


def test_admin_history_omits_kid_with_no_completed_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Finished", "2020-01-01", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Not Done", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin/history")
    assert "Alice" in resp.text
    assert "Bob" not in resp.text
```

Note: `create_assignment`, `create_user`, `_login` are already imported/defined in both test files — no new imports needed for these tests specifically (Task 3's step already added `get_assignment_by_id`/`list_assignments_for_user` to `test_overview_routes.py`'s import line).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: FAIL — `/overview/history` and `/admin/history` don't exist yet (404)

- [ ] **Step 3: Append the two list functions to `app/assignments.py`**

Add at the end of the file, after `sort_by_priority`:

```python


def list_completed_assignments_for_user(conn: sqlite3.Connection, user_id: int) -> list[Assignment]:
    rows = conn.execute(
        "SELECT * FROM assignments WHERE user_id = ? AND status = 'done' "
        "ORDER BY completed_at DESC",
        (user_id,),
    ).fetchall()
    return [_row_to_assignment(row) for row in rows]


def list_all_completed_assignments(conn: sqlite3.Connection) -> list[Assignment]:
    rows = conn.execute(
        "SELECT * FROM assignments WHERE status = 'done' ORDER BY completed_at DESC"
    ).fetchall()
    return [_row_to_assignment(row) for row in rows]
```

- [ ] **Step 4: Add the history route to `app/routers/overview.py`**

Add `list_completed_assignments_for_user` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    Assignment,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_assignments_for_user,
    list_completed_assignments_for_user,
    sort_by_priority,
    update_assignment,
)
```

Add this new route function anywhere after the `overview()` function (e.g. right before `add_assignment`):

```python
@router.get("/overview/history", response_class=HTMLResponse)
def overview_history(
    request: Request,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    completed = list_completed_assignments_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview_history.html",
        {
            "request": request,
            "user": user,
            "completed": completed,
        },
    )
```

- [ ] **Step 5: Add the history route to `app/routers/admin.py`**

Add `list_all_completed_assignments` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    list_all_completed_assignments,
    sort_by_priority,
    update_assignment,
)
```

Add this new route function anywhere after `admin_dashboard()`:

```python
@router.get("/admin/history", response_class=HTMLResponse)
def admin_history(
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    completed = list_all_completed_assignments(db)

    completed_by_kid_id: dict[int, list] = {}
    for a in completed:
        completed_by_kid_id.setdefault(a.user_id, []).append(a)

    all_users = list_users(db)
    groups = [
        (user, completed_by_kid_id[user.id])
        for user in all_users
        if user.id in completed_by_kid_id
    ]

    return templates.TemplateResponse(
        "admin_history.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
        },
    )
```

- [ ] **Step 6: Add the History nav link to `app/templates/base.html`**

Replace:

```html
            {% if user.is_admin %}
                <a href="/admin">All assignments</a>
                <a href="/admin/users">Manage users</a>
                <a href="/admin/classes">Manage classes</a>
            {% else %}
                <a href="/overview">My assignments</a>
            {% endif %}
```

with:

```html
            {% if user.is_admin %}
                <a href="/admin">All assignments</a>
                <a href="/admin/history">History</a>
                <a href="/admin/users">Manage users</a>
                <a href="/admin/classes">Manage classes</a>
            {% else %}
                <a href="/overview">My assignments</a>
                <a href="/overview/history">History</a>
            {% endif %}
```

- [ ] **Step 7: Create `app/templates/overview_history.html`**

```html
{% extends "base.html" %}
{% block title %}History — Homework Manager{% endblock %}
{% block content %}
<h1>Completed work</h1>

<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Completed</th><th></th></tr>
    </thead>
    <tbody>
        {% for a in completed %}
        <tr>
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
            <td>{{ a.due_date }}</td>
            <td>{{ a.completed_at }}</td>
            <td><a href="/overview/{{ a.id }}/edit">Edit</a></td>
        </tr>
        {% else %}
        <tr><td colspan="5">Nothing finished yet.</td></tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 8: Create `app/templates/admin_history.html`**

```html
{% extends "base.html" %}
{% block title %}History — Homework Manager{% endblock %}
{% block content %}
<h1>Completed work</h1>

{% for kid, kid_completed in groups %}
<h2>{{ kid.display_name }}</h2>
<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Completed</th><th></th></tr>
    </thead>
    <tbody>
        {% for a in kid_completed %}
        <tr>
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
            <td>{{ a.due_date }}</td>
            <td>{{ a.completed_at }}</td>
            <td><a href="/admin/{{ a.id }}/edit">Edit</a></td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<p>Nothing finished yet.</p>
{% endfor %}
{% endblock %}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: PASS (all tests, including the 9 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 10: Commit**

```bash
git add app/assignments.py app/routers/overview.py app/routers/admin.py app/templates/base.html app/templates/overview_history.html app/templates/admin_history.html tests/test_overview_routes.py tests/test_admin_routes.py
git commit -m "feat: add completed-work history views"
```

---

### Task 5: On-time streak stats

**Files:**
- Modify: `app/assignments.py` (add import, append one function)
- Modify: `app/routers/overview.py`
- Modify: `app/routers/admin.py`
- Modify: `app/templates/overview.html`
- Modify: `app/templates/admin.html`
- Modify: `app/static/style.css`
- Test: `tests/test_assignments.py`, `tests/test_overview_routes.py`, `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `Assignment.completed_at`/`due_date` from Task 2.
- Produces: `compute_streak(conn, user_id, today: str) -> int` in `app/assignments.py`. `overview()`'s template context gains `streak: int`. `admin_dashboard()`'s template context gains `kid_streaks: dict[int, int]` (keyed by user id).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_assignments.py` (add `compute_streak` to the existing import block at the top of the file first — change `from app.assignments import (\n    VALID_STATUSES,\n    create_assignment,\n    delete_assignment,\n    get_assignment_by_id,\n    list_all_assignments,\n    list_assignments_for_user,\n    update_assignment,\n)` to also include `compute_streak,` in the alphabetically-sorted list):

```python
def test_compute_streak_zero_with_no_assignments(db, make_user):
    kid = make_user("kid1")
    assert compute_streak(db, kid.id, "2026-09-20") == 0


def test_compute_streak_counts_consecutive_on_time_days(db, make_user):
    kid = make_user("kid1")
    a1 = create_assignment(db, kid.id, "Math", "Day1", "2026-09-18", status="done")
    a2 = create_assignment(db, kid.id, "Math", "Day2", "2026-09-19", status="done")
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-18 10:00:00", a1.id))
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-19 10:00:00", a2.id))
    db.commit()
    assert compute_streak(db, kid.id, "2026-09-20") == 2


def test_compute_streak_stops_at_first_missed_day(db, make_user):
    kid = make_user("kid1")
    a1 = create_assignment(db, kid.id, "Math", "Day1", "2026-09-19", status="done")
    create_assignment(db, kid.id, "Math", "Day2 Not Done", "2026-09-18")
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-19 10:00:00", a1.id))
    db.commit()
    assert compute_streak(db, kid.id, "2026-09-20") == 1


def test_compute_streak_skips_days_with_no_assignments(db, make_user):
    kid = make_user("kid1")
    a1 = create_assignment(db, kid.id, "Math", "Day1", "2026-09-19", status="done")
    a2 = create_assignment(db, kid.id, "Math", "Day3", "2026-09-17", status="done")
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-19 10:00:00", a1.id))
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-17 10:00:00", a2.id))
    db.commit()
    # 2026-09-18 has no assignments due at all, so it's skipped rather than breaking the streak
    assert compute_streak(db, kid.id, "2026-09-20") == 2


def test_compute_streak_breaks_on_late_completion(db, make_user):
    kid = make_user("kid1")
    a1 = create_assignment(db, kid.id, "Math", "Day1", "2026-09-18", status="done")
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-19 10:00:00", a1.id))
    db.commit()
    assert compute_streak(db, kid.id, "2026-09-20") == 0


def test_compute_streak_ignores_assignments_due_today(db, make_user):
    kid = make_user("kid1")
    create_assignment(db, kid.id, "Math", "Due Today Not Done", "2026-09-20")
    a1 = create_assignment(db, kid.id, "Math", "Day1", "2026-09-19", status="done")
    db.execute("UPDATE assignments SET completed_at = ? WHERE id = ?", ("2026-09-19 10:00:00", a1.id))
    db.commit()
    assert compute_streak(db, kid.id, "2026-09-20") == 1
```

Append to `tests/test_overview_routes.py`:

```python
def test_overview_shows_streak_when_positive(client, db):
    from datetime import date, timedelta

    kid = create_user(db, "kid1", "pw", "Kid One")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assignment = create_assignment(db, kid.id, "Math", "Yesterday HW", yesterday, status="done")
    db.execute(
        "UPDATE assignments SET completed_at = ? WHERE id = ?",
        (f"{yesterday} 10:00:00", assignment.id),
    )
    db.commit()
    _login(client, "kid1")
    resp = client.get("/overview")
    assert "1-day streak" in resp.text


def test_overview_hides_streak_when_zero(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert "day streak" not in resp.text
```

Append to `tests/test_admin_routes.py`:

```python
def test_admin_dashboard_shows_kid_streak(client, db):
    from datetime import date, timedelta

    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assignment = create_assignment(db, kid1.id, "Math", "Yesterday HW", yesterday, status="done")
    db.execute(
        "UPDATE assignments SET completed_at = ? WHERE id = ?",
        (f"{yesterday} 10:00:00", assignment.id),
    )
    db.commit()
    _login(client, "parent1")
    resp = client.get("/admin")
    assert "1-day streak" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_assignments.py tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: FAIL — `compute_streak` doesn't exist yet, no streak markup in either page

- [ ] **Step 3: Add the `datetime` import and append `compute_streak` to `app/assignments.py`**

Add to the top of `app/assignments.py`, alongside the existing `import sqlite3`:

```python
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
```

Add this function at the end of the file, after `list_all_completed_assignments`:

```python


def compute_streak(conn: sqlite3.Connection, user_id: int, today: str) -> int:
    """On-time streak: consecutive days walking backward from yesterday where every
    assignment due that day was completed by end of that day. A day with nothing due
    is skipped, not counted as a break."""
    earliest_row = conn.execute(
        "SELECT MIN(due_date) AS earliest FROM assignments WHERE user_id = ?", (user_id,)
    ).fetchone()
    if earliest_row["earliest"] is None:
        return 0
    earliest = date.fromisoformat(earliest_row["earliest"])
    day = date.fromisoformat(today) - timedelta(days=1)

    streak = 0
    while day >= earliest:
        day_str = day.isoformat()
        rows = conn.execute(
            "SELECT completed_at FROM assignments WHERE user_id = ? AND due_date = ?",
            (user_id, day_str),
        ).fetchall()
        if rows:
            all_on_time = all(
                row["completed_at"] is not None and row["completed_at"][:10] <= day_str
                for row in rows
            )
            if not all_on_time:
                break
            streak += 1
        day -= timedelta(days=1)
    return streak
```

- [ ] **Step 4: Show the streak on `app/routers/overview.py`**

Add `compute_streak` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    Assignment,
    compute_streak,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_assignments_for_user,
    list_completed_assignments_for_user,
    sort_by_priority,
    update_assignment,
)
```

In `overview()`, add `"streak": compute_streak(db, user.id, today),` to the template context dict (alongside `"today": today,`).

- [ ] **Step 5: Show each kid's streak on `app/routers/admin.py`**

Add `compute_streak` to the import from `app.assignments`:

```python
from app.assignments import (
    VALID_STATUSES,
    compute_streak,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    list_all_completed_assignments,
    sort_by_priority,
    update_assignment,
)
```

In `admin_dashboard()`, replace:

```python
    all_users = list_users(db)
    groups = [
        (user, assignments_by_kid_id[user.id])
        for user in all_users
        if user.id in assignments_by_kid_id
    ]

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
            "statuses": VALID_STATUSES,
            "selected_status": status_filter,
            "today": today,
        },
    )
```

with:

```python
    all_users = list_users(db)
    groups = [
        (user, assignments_by_kid_id[user.id])
        for user in all_users
        if user.id in assignments_by_kid_id
    ]
    kid_streaks = {user.id: compute_streak(db, user.id, today) for user, _ in groups}

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
            "kid_streaks": kid_streaks,
            "statuses": VALID_STATUSES,
            "selected_status": status_filter,
            "today": today,
        },
    )
```

- [ ] **Step 6: Display the streak in `app/templates/overview.html`**

Replace:

```html
<h1>My assignments</h1>
```

with:

```html
<h1>My assignments</h1>
{% if streak %}<p class="streak">🔥 {{ streak }}-day streak</p>{% endif %}
```

- [ ] **Step 7: Display each kid's streak in `app/templates/admin.html`**

Replace:

```html
{% for kid, kid_assignments in groups %}
<h2>{{ kid.display_name }}</h2>
```

with:

```html
{% for kid, kid_assignments in groups %}
<h2>{{ kid.display_name }}{% if kid_streaks[kid.id] %} <span class="streak">🔥 {{ kid_streaks[kid.id] }}-day streak</span>{% endif %}</h2>
```

- [ ] **Step 8: Add CSS**

Add to `app/static/style.css`, anywhere after the existing rules:

```css
.streak { color: var(--accent); font-weight: bold; }
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_assignments.py tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: PASS (all tests, including the 8 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 10: Commit**

```bash
git add app/assignments.py app/routers/overview.py app/routers/admin.py app/templates/overview.html app/templates/admin.html app/static/style.css tests/test_assignments.py tests/test_overview_routes.py tests/test_admin_routes.py
git commit -m "feat: add on-time streak stats"
```

---

### Task 6: Weekly view

**Files:**
- Create: `app/weeks.py`
- Modify: `app/routers/overview.py` (full-file replacement — this task's changes build on every prior task's changes to this file)
- Modify: `app/routers/admin.py` (full-file replacement — same reason)
- Modify: `app/templates/overview.html` (full-file replacement)
- Modify: `app/templates/admin.html` (full-file replacement)
- Modify: `app/static/style.css`
- Test: `tests/test_weeks.py` (new), `tests/test_overview_routes.py`, `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `sort_by_priority` (Task 3), `compute_streak` (Task 5), `list_completed_assignments_for_user`/`list_all_completed_assignments` (Task 4) — all already wired into these two router files by prior tasks.
- Produces: `current_week_start(today: date) -> date`, `week_dates(week_start: date) -> list[date]`, `group_assignments_by_day(assignments, dates: list[date]) -> list[tuple[date, list[Assignment]]]` in `app/weeks.py` — pure functions, no DB access. `overview()` and `admin_dashboard()` both gain `view: str = "list"` and `week: Optional[str] = None` query params and pass `day_groups`/`week_groups`, `prev_week`, `next_week` into their template context.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weeks.py`:

```python
from dataclasses import dataclass
from datetime import date

from app.weeks import current_week_start, group_assignments_by_day, week_dates


def test_current_week_start_on_sunday_returns_same_day():
    assert current_week_start(date(2026, 9, 20)) == date(2026, 9, 20)  # a Sunday


def test_current_week_start_on_wednesday_returns_preceding_sunday():
    assert current_week_start(date(2026, 9, 23)) == date(2026, 9, 20)  # a Wednesday


def test_current_week_start_on_saturday_returns_preceding_sunday():
    assert current_week_start(date(2026, 9, 26)) == date(2026, 9, 20)  # a Saturday


def test_week_dates_returns_seven_consecutive_days_from_sunday():
    dates = week_dates(date(2026, 9, 20))
    assert dates == [date(2026, 9, 20 + i) for i in range(7)]


def test_group_assignments_by_day_buckets_by_due_date():
    @dataclass
    class FakeAssignment:
        due_date: str

    dates = week_dates(date(2026, 9, 20))
    assignments = [FakeAssignment(due_date="2026-09-22"), FakeAssignment(due_date="2026-09-22")]
    grouped = group_assignments_by_day(assignments, dates)

    assert len(grouped) == 7
    tuesday_date, tuesday_items = grouped[2]
    assert tuesday_date == date(2026, 9, 22)
    assert len(tuesday_items) == 2
    monday_date, monday_items = grouped[1]
    assert monday_date == date(2026, 9, 21)
    assert monday_items == []
```

Append to `tests/test_overview_routes.py`:

```python
def test_overview_list_view_is_default_and_unchanged(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert resp.status_code == 200
    assert "<table>" in resp.text
    assert "week-grid" not in resp.text


def test_overview_week_view_shows_assignment_under_correct_day(client, db):
    from datetime import date, timedelta

    kid = create_user(db, "kid1", "pw", "Kid One")
    week_start = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)
    wednesday = (week_start + timedelta(days=3)).isoformat()
    create_assignment(db, kid.id, "Math", "Wednesday HW", wednesday)
    _login(client, "kid1")
    resp = client.get("/overview?view=week")
    assert resp.status_code == 200
    assert "week-grid" in resp.text
    assert "Wednesday HW" in resp.text


def test_overview_week_navigation_moves_the_window(client, db):
    from datetime import date, timedelta

    kid = create_user(db, "kid1", "pw", "Kid One")
    week_start = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)
    next_week_start = week_start + timedelta(days=7)
    next_week_wednesday = (next_week_start + timedelta(days=3)).isoformat()
    create_assignment(db, kid.id, "Math", "Next Week HW", next_week_wednesday)
    _login(client, "kid1")
    resp = client.get("/overview?view=week")
    assert "Next Week HW" not in resp.text
    resp2 = client.get(f"/overview?view=week&week={next_week_start.isoformat()}")
    assert "Next Week HW" in resp2.text
```

Append to `tests/test_admin_routes.py`:

```python
def test_admin_dashboard_list_view_is_default_and_unchanged(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")
    _login(client, "parent1")
    resp = client.get("/admin")
    assert "<table>" in resp.text
    assert "week-grid" not in resp.text


def test_admin_dashboard_week_view_shows_assignment_under_correct_day(client, db):
    from datetime import date, timedelta

    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    week_start = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)
    wednesday = (week_start + timedelta(days=3)).isoformat()
    create_assignment(db, kid1.id, "Math", "Wednesday HW", wednesday)
    _login(client, "parent1")
    resp = client.get("/admin?view=week")
    assert resp.status_code == 200
    assert "week-grid" in resp.text
    assert "Wednesday HW" in resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_weeks.py tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: FAIL — `app/weeks.py` doesn't exist yet (import error), no `view=week` handling on either route

- [ ] **Step 3: Create `app/weeks.py`**

```python
from datetime import date, timedelta


def current_week_start(today: date) -> date:
    """Sunday of the week containing `today`."""
    return today - timedelta(days=(today.weekday() + 1) % 7)


def week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def group_assignments_by_day(assignments, dates: list[date]) -> list[tuple[date, list]]:
    by_date: dict[str, list] = {}
    for a in assignments:
        by_date.setdefault(a.due_date, []).append(a)
    return [(d, by_date.get(d.isoformat(), [])) for d in dates]
```

- [ ] **Step 4: Replace `app/routers/overview.py` in full**

```python
import sqlite3
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.assignments import (
    VALID_STATUSES,
    Assignment,
    compute_streak,
    create_assignment,
    delete_assignment,
    get_assignment_by_id,
    list_assignments_for_user,
    list_completed_assignments_for_user,
    sort_by_priority,
    update_assignment,
)
from app.classes import list_active_classes_for_user
from app.deps import get_db, require_user
from app.users import User
from app.weeks import current_week_start, group_assignments_by_day, week_dates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _visible_assignments(assignments: list[Assignment], today: str) -> list[Assignment]:
    """Drop assignments marked done once their due date has arrived."""
    return [a for a in assignments if not (a.status == "done" and a.due_date <= today)]


@router.get("/overview", response_class=HTMLResponse)
def overview(
    request: Request,
    view: str = "list",
    week: Optional[str] = None,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    today = date.today().isoformat()
    assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
    active_classes = list_active_classes_for_user(db, user.id)
    streak = compute_streak(db, user.id, today)

    week_start_date = date.fromisoformat(week) if week else current_week_start(date.today())
    dates = week_dates(week_start_date)
    day_groups = group_assignments_by_day(assignments, dates)
    prev_week = (week_start_date - timedelta(days=7)).isoformat()
    next_week = (week_start_date + timedelta(days=7)).isoformat()

    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "statuses": VALID_STATUSES,
            "active_classes": active_classes,
            "today": today,
            "streak": streak,
            "view": view,
            "day_groups": day_groups,
            "prev_week": prev_week,
            "next_week": next_week,
        },
    )


@router.get("/overview/history", response_class=HTMLResponse)
def overview_history(
    request: Request,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    completed = list_completed_assignments_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview_history.html",
        {
            "request": request,
            "user": user,
            "completed": completed,
        },
    )


@router.post("/overview/add")
def add_assignment(
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    active_classes = list_active_classes_for_user(db, user.id)
    today = date.today().isoformat()
    if not (subject and subject.strip()) or not (title and title.strip()) or not (
        due_date and due_date.strip()
    ):
        assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
        return templates.TemplateResponse(
            "overview.html",
            {
                "request": request,
                "user": user,
                "assignments": assignments,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "today": today,
                "streak": compute_streak(db, user.id, today),
                "view": "list",
                "error": "Subject, title, and due date are all required.",
                "form_subject": subject or "",
                "form_title": title or "",
                "form_due_date": due_date or "",
                "form_priority": bool(priority),
            },
            status_code=400,
        )
    if active_classes and subject not in {c.name for c in active_classes}:
        assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
        return templates.TemplateResponse(
            "overview.html",
            {
                "request": request,
                "user": user,
                "assignments": assignments,
                "statuses": VALID_STATUSES,
                "active_classes": active_classes,
                "today": today,
                "streak": compute_streak(db, user.id, today),
                "view": "list",
                "error": "Please choose a subject from the list.",
                "form_subject": subject,
                "form_title": title,
                "form_due_date": due_date,
                "form_priority": bool(priority),
            },
            status_code=400,
        )
    create_assignment(db, user.id, subject, title, due_date, priority=bool(priority))
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
        db,
        assignment.id,
        assignment.subject,
        assignment.title,
        assignment.due_date,
        status,
        assignment.priority,
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
            "form_priority": assignment.priority,
        },
    )


@router.post("/overview/{assignment_id}/edit")
def edit_assignment(
    assignment_id: int,
    request: Request,
    subject: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
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
                "form_priority": bool(priority),
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
                "form_priority": bool(priority),
            },
            status_code=400,
        )
    update_assignment(db, assignment.id, subject, title, due_date, assignment.status, bool(priority))
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

- [ ] **Step 5: Replace `app/routers/admin.py` in full**

```python
import sqlite3
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.assignments import (
    VALID_STATUSES,
    compute_streak,
    delete_assignment,
    get_assignment_by_id,
    list_all_assignments,
    list_all_completed_assignments,
    sort_by_priority,
    update_assignment,
)
from app.classes import list_active_classes_for_user
from app.deps import get_db, require_admin
from app.users import User, list_users
from app.weeks import current_week_start, group_assignments_by_day, week_dates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    status: Optional[str] = None,
    view: str = "list",
    week: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    today = date.today().isoformat()
    assignments = [
        a for a in list_all_assignments(db) if not (a.status == "done" and a.due_date <= today)
    ]

    status_filter = status if status else None
    if status_filter is not None:
        assignments = [a for a in assignments if a.status == status_filter]

    assignments = sort_by_priority(assignments)

    assignments_by_kid_id: dict[int, list] = {}
    for a in assignments:
        assignments_by_kid_id.setdefault(a.user_id, []).append(a)

    all_users = list_users(db)
    groups = [
        (user, assignments_by_kid_id[user.id])
        for user in all_users
        if user.id in assignments_by_kid_id
    ]
    kid_streaks = {user.id: compute_streak(db, user.id, today) for user, _ in groups}

    week_start_date = date.fromisoformat(week) if week else current_week_start(date.today())
    dates = week_dates(week_start_date)
    week_groups = [
        (user, group_assignments_by_day(kid_assignments, dates))
        for user, kid_assignments in groups
    ]
    prev_week = (week_start_date - timedelta(days=7)).isoformat()
    next_week = (week_start_date + timedelta(days=7)).isoformat()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
            "week_groups": week_groups,
            "kid_streaks": kid_streaks,
            "statuses": VALID_STATUSES,
            "selected_status": status_filter,
            "today": today,
            "view": view,
            "prev_week": prev_week,
            "next_week": next_week,
        },
    )


@router.get("/admin/history", response_class=HTMLResponse)
def admin_history(
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    completed = list_all_completed_assignments(db)

    completed_by_kid_id: dict[int, list] = {}
    for a in completed:
        completed_by_kid_id.setdefault(a.user_id, []).append(a)

    all_users = list_users(db)
    groups = [
        (user, completed_by_kid_id[user.id])
        for user in all_users
        if user.id in completed_by_kid_id
    ]

    return templates.TemplateResponse(
        "admin_history.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
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
        db,
        assignment.id,
        assignment.subject,
        assignment.title,
        assignment.due_date,
        status,
        assignment.priority,
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
            "form_priority": assignment.priority,
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
    priority: Optional[str] = Form(None),
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
                "form_priority": bool(priority),
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
                "form_priority": bool(priority),
            },
            status_code=400,
        )
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    update_assignment(db, assignment.id, subject, title, due_date, status, bool(priority))
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

- [ ] **Step 6: Replace `app/templates/overview.html` in full**

```html
{% extends "base.html" %}
{% block title %}My Assignments — Homework Manager{% endblock %}
{% block content %}
<h1>My assignments</h1>
{% if streak %}<p class="streak">🔥 {{ streak }}-day streak</p>{% endif %}

<p class="view-toggle">
    <a href="/overview?view=list" class="{% if view != 'week' %}active{% endif %}">List</a>
    <a href="/overview?view=week" class="{% if view == 'week' %}active{% endif %}">This Week</a>
</p>

{% if view == 'week' %}
<p class="week-nav">
    <a href="/overview?view=week&week={{ prev_week }}">&laquo; Previous week</a>
    <a href="/overview?view=week&week={{ next_week }}">Next week &raquo;</a>
</p>
<div class="week-grid">
    {% for day, day_assignments in day_groups %}
    <div class="week-day">
        <h3>{{ day.strftime('%a %m/%d') }}</h3>
        {% for a in day_assignments %}
        <div class="week-item status-{{ a.status }}{% if a.due_date < today and a.status != 'done' %} overdue{% endif %}">
            {% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}<strong>{{ a.subject }}</strong>: {{ a.title }}
        </div>
        {% else %}
        <p class="empty">—</p>
        {% endfor %}
    </div>
    {% endfor %}
</div>
{% else %}
<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Status</th><th></th><th></th></tr>
    </thead>
    <tbody>
        {% for a in assignments %}
        <tr {% if a.due_date < today and a.status != 'done' %}class="overdue"{% endif %}>
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
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
            <td><a href="/overview/{{ a.id }}/edit">Edit</a></td>
            <td>
                <form method="post" action="/overview/{{ a.id }}/delete" class="inline">
                    <button type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="6">Nothing due — you're all caught up.</td></tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}

<h2>Add an assignment</h2>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" action="/overview/add" class="stack">
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
    <label>Title <input type="text" name="title" value="{{ form_title or '' }}" required></label>
    <label>Due date <input type="date" name="due_date" value="{{ form_due_date or '' }}" required></label>
    <label class="checkbox"><input type="checkbox" name="priority" value="1" {% if form_priority %}checked{% endif %}> Important</label>
    <button type="submit">Add</button>
</form>
{% endblock %}
```

- [ ] **Step 7: Replace `app/templates/admin.html` in full**

```html
{% extends "base.html" %}
{% block title %}All Assignments — Homework Manager{% endblock %}
{% block content %}
<h1>All assignments</h1>

<form method="get" action="/admin" class="stack">
    <label>Status
        <select name="status" onchange="this.form.submit()">
            <option value="">All statuses</option>
            {% for s in statuses %}
            <option value="{{ s }}" {% if selected_status == s %}selected{% endif %}>{{ s.replace('_', ' ') }}</option>
            {% endfor %}
        </select>
    </label>
</form>

<p class="view-toggle">
    <a href="/admin?status={{ selected_status or '' }}&view=list" class="{% if view != 'week' %}active{% endif %}">List</a>
    <a href="/admin?status={{ selected_status or '' }}&view=week" class="{% if view == 'week' %}active{% endif %}">This Week</a>
</p>

{% if view == 'week' %}
<p class="week-nav">
    <a href="/admin?status={{ selected_status or '' }}&view=week&week={{ prev_week }}">&laquo; Previous week</a>
    <a href="/admin?status={{ selected_status or '' }}&view=week&week={{ next_week }}">Next week &raquo;</a>
</p>
{% for kid, day_groups in week_groups %}
<h2>{{ kid.display_name }}{% if kid_streaks[kid.id] %} <span class="streak">🔥 {{ kid_streaks[kid.id] }}-day streak</span>{% endif %}</h2>
<div class="week-grid">
    {% for day, day_assignments in day_groups %}
    <div class="week-day">
        <h3>{{ day.strftime('%a %m/%d') }}</h3>
        {% for a in day_assignments %}
        <div class="week-item status-{{ a.status }}{% if a.due_date < today and a.status != 'done' %} overdue{% endif %}">
            {% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}<strong>{{ a.subject }}</strong>: {{ a.title }}
        </div>
        {% else %}
        <p class="empty">—</p>
        {% endfor %}
    </div>
    {% endfor %}
</div>
{% else %}
<p>No assignments logged yet.</p>
{% endfor %}
{% else %}
{% for kid, kid_assignments in groups %}
<h2>{{ kid.display_name }}{% if kid_streaks[kid.id] %} <span class="streak">🔥 {{ kid_streaks[kid.id] }}-day streak</span>{% endif %}</h2>
<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Status</th><th></th><th></th></tr>
    </thead>
    <tbody>
        {% for a in kid_assignments %}
        <tr {% if a.due_date < today and a.status != 'done' %}class="overdue"{% endif %}>
            <td>{{ a.subject }}</td>
            <td>{% if a.priority %}<span class="priority-mark" title="Important">★</span> {% endif %}{{ a.title }}</td>
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
            <td><a href="/admin/{{ a.id }}/edit">Edit</a></td>
            <td>
                <form method="post" action="/admin/{{ a.id }}/delete" class="inline">
                    <button type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<p>No assignments logged yet.</p>
{% endfor %}
{% endif %}
{% endblock %}
```

- [ ] **Step 8: Add CSS**

Add to `app/static/style.css`, anywhere after the existing rules:

```css
.view-toggle a { margin-right: 0.75rem; }
.view-toggle a.active { font-weight: bold; text-decoration: underline; }
.week-nav a { margin-right: 1rem; }
.week-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.5rem; margin-top: 1rem; }
.week-day { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.5rem; min-height: 4rem; }
.week-day h3 { margin: 0 0 0.4rem; font-size: 0.85rem; }
.week-item { font-size: 0.85rem; padding: 0.2rem 0; }
.week-item.overdue { color: var(--error); }
.week-day .empty { color: var(--border); margin: 0; }
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_weeks.py tests/test_overview_routes.py tests/test_admin_routes.py -v`
Expected: PASS (all tests, including the 8 new ones)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 10: Commit**

```bash
git add app/weeks.py app/routers/overview.py app/routers/admin.py app/templates/overview.html app/templates/admin.html app/static/style.css tests/test_weeks.py tests/test_overview_routes.py tests/test_admin_routes.py
git commit -m "feat: add weekly calendar view alongside the flat list"
```

---

## Self-Review Notes

- **Spec coverage:** data model (`priority`, `completed_at` columns + migration) — Task 1; `completed_at` tracking semantics (set on becoming done, cleared on leaving done, unchanged on done-to-done no-op) — Task 2; priority checkbox on add/edit forms, marker, sort-to-top preserving due-date order within tier — Task 3; `/overview/history` and `/admin/history` routes, own-vs-all visibility, Edit link preserved so a mistaken "done" can be corrected — Task 4; on-time streak definition (walks backward from yesterday, skips empty days, breaks on a missed or late day, displayed on both the kid's own page and next to each kid on admin) — Task 5; Sun–Sat weekly view as a toggle alongside (not replacing) the list, prev/next navigation via `week=` — Task 6. Every spec requirement maps to a task.
- **Placeholder scan:** no TBD/TODO; every step has literal code, not a description of code.
- **Type consistency:** `priority: bool` and `completed_at: Optional[str]` are consistent across `Assignment`, `create_assignment`, `update_assignment`, and every template's `a.priority`/`a.completed_at` access from Task 2 onward. `sort_by_priority(assignments: list[Assignment]) -> list[Assignment]` (Task 3) is reused unchanged by Task 6's week-view grouping — it's applied before `group_assignments_by_day`, so day buckets inherit the same priority-first ordering. `compute_streak(conn, user_id: int, today: str) -> int` (Task 5) matches the `today: str` (ISO date) type already used everywhere else in both routers. `week_dates`/`group_assignments_by_day` (Task 6) consistently use `datetime.date` objects for calendar math and `.isoformat()` strings only at the DB/template boundary, matching how `due_date`/`today` are stored and compared elsewhere in the app (plain string comparison, zero-padded `YYYY-MM-DD`).


---
