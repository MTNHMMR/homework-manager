# Overdue Highlighting and Admin Kid-Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Highlight overdue (past-due, not-done) assignments on both the kid's own page and the admin dashboard, and group the admin dashboard's assignment list by kid instead of showing one flat sorted list.

**Architecture:** No schema change. Each affected route computes `today` (an ISO date string) and passes it to its template, which marks a row `overdue` via a plain string comparison against `due_date` — the same assumption the existing `ORDER BY due_date` sort already relies on. The admin route additionally re-shapes its already-fetched, already-sorted assignment list into per-kid groups before rendering, and drops the now-redundant `kid_id` query-filter entirely.

**Tech Stack:** Same as the existing app — Python/FastAPI, Jinja2, stdlib `sqlite3`/`datetime`, pytest + httpx `TestClient`. No new dependencies.

## Global Constraints

- An assignment is **overdue** when `due_date < today` AND `status != 'done'` — a done assignment is never marked overdue, regardless of date.
- `today` is computed server-side via `date.today().isoformat()`, once per request, in the route — never in the template.
- Overdue styling is a background tint on the whole `<tr>` (`color-mix(in srgb, var(--error) 12%, var(--card-bg))`) — never a `display`-altering rule on a `<td>`. A prior change that put `display: inline-block` directly on a `<td>` broke the table's row-height/border rendering around the status dropdown; row-level `background-color` cannot repeat that failure since it doesn't touch layout at all.
- The admin dashboard's "Kid" filter (`kid_id` query param and its `<select>`) is removed entirely — grouping already shows every kid's work under its own heading, so a separate single-kid filter is redundant. The "Status" filter stays and narrows the assignment set *before* grouping, so a kid with zero assignments matching the current status filter gets no heading at all (not an empty one).
- Within each kid's group on `/admin`, assignments stay sorted by due date. `list_all_assignments` already returns everything sorted by `due_date` globally — bucketing that list by `user_id` in a single pass preserves each kid's relative due-date order, so no additional sort is needed.
- Kids are grouped in the same order `/admin/users` and `/admin/classes` already list them: `ORDER BY display_name` (i.e., iterate `list_users()` and skip admins, same as the existing `kids` variable already did before this change).

---

## File Structure

```
app/
  routers/
    overview.py   # MODIFY — GET /overview computes and passes `today`
    admin.py       # MODIFY — GET /admin drops kid_id, groups by kid, passes `today`
  templates/
    overview.html    # MODIFY — row-level overdue class
    admin.html         # MODIFY — remove Kid filter, render grouped-by-kid tables, row-level overdue class
  static/
    style.css           # MODIFY — add `.overdue` rule
tests/
  test_overview_routes.py   # MODIFY — overdue tests
  test_admin_routes.py        # MODIFY — remove 3 kid_id-specific tests, add grouping + overdue tests
```

---

### Task 1: Overdue highlighting on the kid's own overview page

**Files:**
- Modify: `app/routers/overview.py`
- Modify: `app/templates/overview.html`
- Modify: `app/static/style.css`
- Test: `tests/test_overview_routes.py`

**Interfaces:**
- Consumes: nothing new from other tasks — this task is self-contained.
- Produces: `GET /overview`'s template context gains a `today` key (ISO date string). No function signatures change; `overview.html`'s row markup gains a conditional `class="overdue"`. Task 2 (admin dashboard) follows the identical pattern independently — it does not import anything from this task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_overview_routes.py — add these to the existing file
def test_overview_marks_overdue_not_done_assignment_with_overdue_class(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Overdue HW", "2020-01-01")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' in resp.text


def test_overview_does_not_mark_done_assignment_overdue(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Finished HW", "2020-01-01", status="done")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' not in resp.text


def test_overview_does_not_mark_future_assignment_overdue(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Future HW", "2099-01-01")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' not in resp.text


def test_overview_marks_overdue_in_progress_assignment_too(client, db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    create_assignment(db, kid.id, "Math", "Started HW", "2020-01-01", status="in_progress")
    _login(client, "kid1")
    resp = client.get("/overview")
    assert 'class="overdue"' in resp.text
```

Note: `create_user`, `create_assignment`, and `_login` are already imported/defined at the top of `tests/test_overview_routes.py` — no new imports needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_overview_routes.py -v`
Expected: FAIL — `overdue` never appears anywhere in the current response

- [ ] **Step 3: Update `app/routers/overview.py`**

Add the import and the `today` context variable to the `overview` function only (every other function in this file is unchanged):

```python
# At the top of the file, add to the existing imports:
from datetime import date

# ... (all other existing imports stay exactly as they are)


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
            "today": date.today().isoformat(),
        },
    )
```

(Every other function in `app/routers/overview.py` — `add_assignment`, `_own_assignment_or_403`, `set_status`, `edit_assignment_form`, `edit_assignment`, `delete_own` — is unchanged. This task only touches the `overview` GET handler.)

- [ ] **Step 4: Update the row markup in `app/templates/overview.html`**

Replace:

```html
        {% for a in assignments %}
        <tr>
```

with:

```html
        {% for a in assignments %}
        <tr {% if a.due_date < today and a.status != 'done' %}class="overdue"{% endif %}>
```

(Nothing else in this template changes — the rest of the row, the "Add an assignment" form, and everything else stays exactly as it is.)

- [ ] **Step 5: Add the CSS rule**

Add this line to `app/static/style.css`, anywhere after the `:root`/`body[data-theme=...]` blocks (e.g. right after the existing `.status-not_started { color: var(--status-idle); }` line — exact placement doesn't matter, it's a standalone rule):

```css
tr.overdue { background: color-mix(in srgb, var(--error) 12%, var(--card-bg)); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_overview_routes.py -v`
Expected: PASS (all tests, including the 4 new ones)

Run: `pytest -v`
Expected: PASS (full suite — confirms nothing else broke)

- [ ] **Step 7: Commit**

```bash
git add app/routers/overview.py app/templates/overview.html app/static/style.css tests/test_overview_routes.py
git commit -m "feat: highlight overdue assignments on the kid overview page"
```

---

### Task 2: Overdue highlighting and kid-grouping on the admin dashboard

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `app/templates/admin.html`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: nothing from Task 1 — this task independently adds its own `today` context variable following the identical pattern, and the `.overdue` CSS rule Task 1 already added to `app/static/style.css` (shared, no further CSS change needed here).
- Produces: `GET /admin` no longer accepts/uses a `kid_id` query parameter. Its template context changes shape: the old `assignments` (flat list), `users_by_id`, `kids`, `selected_kid_id` keys are replaced by a single `groups` key — a list of `(User, list[Assignment])` tuples, one per kid that has at least one assignment matching the current status filter, in kid display-name order. `selected_status` and `statuses` are unchanged. `today` is added, same meaning as Task 1.

- [ ] **Step 1: Remove the three tests that exercise the `kid_id` filter being removed**

Delete these three test functions entirely from `tests/test_admin_routes.py` (they test behavior this task removes on purpose):
- `test_admin_dashboard_filters_by_kid`
- `test_admin_dashboard_reset_kid_filter_shows_everyone`
- `test_admin_dashboard_ignores_non_numeric_kid_id`

Leave every other test in the file untouched for now — `test_admin_dashboard_shows_all_kids_assignments` and `test_admin_dashboard_filters_by_status`/`test_admin_dashboard_reset_status_filter_shows_everyone` still apply and should still pass once this task is done (grouping doesn't change what text appears on the page, only how it's organized).

- [ ] **Step 2: Write the new failing tests**

```python
# tests/test_admin_routes.py — add these to the existing file
def test_admin_dashboard_groups_assignments_by_kid(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Worksheet", "2026-09-25")
    create_assignment(db, kid2.id, "Science", "Bob Lab", "2026-09-26")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert resp.status_code == 200
    # Alice's heading and assignment appear before Bob's (display-name order)
    alice_pos = resp.text.index("Alice")
    bob_pos = resp.text.index("Bob")
    assert alice_pos < bob_pos
    assert "Alice Worksheet" in resp.text
    assert "Bob Lab" in resp.text


def test_admin_dashboard_omits_kid_with_no_matching_assignments(client, db):
    kid1 = create_user(db, "kid1", "pw", "Alice")
    kid2 = create_user(db, "kid2", "pw", "Bob")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Alice Worksheet", "2026-09-25", status="done")
    create_assignment(db, kid2.id, "Science", "Bob Lab", "2026-09-26", status="not_started")

    _login(client, "parent1")
    resp = client.get("/admin?status=not_started")
    assert "Bob" in resp.text
    assert "Bob Lab" in resp.text
    assert "Alice" not in resp.text


def test_admin_dashboard_kid_id_query_param_is_ignored(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Worksheet", "2026-09-25")

    _login(client, "parent1")
    resp = client.get("/admin?kid_id=999")
    assert resp.status_code == 200
    assert "Worksheet" in resp.text


def test_admin_dashboard_marks_overdue_not_done_assignment(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Overdue HW", "2020-01-01")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="overdue"' in resp.text


def test_admin_dashboard_does_not_mark_done_assignment_overdue(client, db):
    kid1 = create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    create_assignment(db, kid1.id, "Math", "Finished HW", "2020-01-01", status="done")

    _login(client, "parent1")
    resp = client.get("/admin")
    assert 'class="overdue"' not in resp.text
```

Note: `create_user`, `create_assignment`, `_login` are already imported/defined at the top of `tests/test_admin_routes.py` — no new imports needed.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_admin_routes.py -v`
Expected: the 3 deleted tests are gone (no longer collected); the 5 new tests FAIL (grouping/overdue don't exist yet, and `kid_id=999` currently filters everything out via the existing `kid_id` handling rather than being ignored)

- [ ] **Step 4: Update `app/routers/admin.py`**

Replace the entire file with:

```python
import sqlite3
from datetime import date
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
    status: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    assignments = list_all_assignments(db)

    status_filter = status if status else None
    if status_filter is not None:
        assignments = [a for a in assignments if a.status == status_filter]

    assignments_by_kid_id: dict[int, list] = {}
    for a in assignments:
        assignments_by_kid_id.setdefault(a.user_id, []).append(a)

    kids = [u for u in list_users(db) if not u.is_admin]
    groups = [
        (kid, assignments_by_kid_id[kid.id])
        for kid in kids
        if kid.id in assignments_by_kid_id
    ]

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "groups": groups,
            "statuses": VALID_STATUSES,
            "selected_status": status_filter,
            "today": date.today().isoformat(),
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

(Only `admin_dashboard` changed — `admin_set_status`, `admin_edit_form`, `admin_edit`, `admin_delete` are copied verbatim from the current file, unchanged, so the full-file replacement doesn't lose anything.)

- [ ] **Step 5: Replace `app/templates/admin.html` in full**

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

{% for kid, kid_assignments in groups %}
<h2>{{ kid.display_name }}</h2>
<table>
    <thead>
        <tr><th>Subject</th><th>Title</th><th>Due</th><th>Status</th><th></th><th></th></tr>
    </thead>
    <tbody>
        {% for a in kid_assignments %}
        <tr {% if a.due_date < today and a.status != 'done' %}class="overdue"{% endif %}>
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
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_admin_routes.py -v`
Expected: PASS (all remaining/new tests)

Run: `pytest -v`
Expected: PASS (full suite)

- [ ] **Step 7: Commit**

```bash
git add app/routers/admin.py app/templates/admin.html tests/test_admin_routes.py
git commit -m "feat: group admin dashboard by kid and highlight overdue assignments"
```

---

## Self-Review Notes

- **Spec coverage:** overdue definition (past-due AND not done) — Tasks 1 & 2; both pages covered — Task 1 (`/overview`), Task 2 (`/admin`); row-level (not `<td>`-level) styling to avoid the table-layout bug — Task 1 Step 5 CSS rule, reused by Task 2; kid grouping in display-name order — Task 2 Step 4; kids with no matching assignments get no heading — Task 2 Step 4 (`if kid.id in assignments_by_kid_id`); Kid filter removed — Task 2 Step 4 (no `kid_id` param at all); Status filter still works and applies before grouping — Task 2 Step 4 (`status_filter` applied to `assignments` before bucketing). Every spec requirement maps to a task.
- **Placeholder scan:** no TBD/TODO; every step has literal code, not a description of code.
- **Type consistency:** `today` is a plain `str` (ISO date) in both tasks, matching the existing `due_date: str` field on `Assignment` it's compared against — same type, safe `<` comparison. `groups` is `list[tuple[User, list[Assignment]]]`, consumed by the template via `{% for kid, kid_assignments in groups %}`, matching how it's constructed in Step 4.
