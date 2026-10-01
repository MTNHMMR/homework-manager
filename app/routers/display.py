import sqlite3
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.assignments import list_all_assignments
from app.deps import get_db, require_admin
from app.display_tokens import (
    create_display_token,
    list_display_tokens,
    revoke_display_token,
    verify_display_token,
)
from app.users import User, list_users
from app.templating import templates

router = APIRouter()

MAX_DAYS = 31


def _render_page(request: Request, admin: User, db: sqlite3.Connection, **extra):
    return templates.TemplateResponse(
        "admin_display.html",
        {"request": request, "user": admin, "tokens": list_display_tokens(db), **extra},
    )


@router.get("/admin/display", response_class=HTMLResponse)
def display_access(
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    return _render_page(request, admin, db)


@router.post("/admin/display/tokens", response_class=HTMLResponse)
def add_display_token(
    request: Request,
    name: str = Form(...),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    record, token = create_display_token(db, name.strip() or "Display")
    # Rendered directly (no redirect) because this is the only time the plaintext
    # token exists; it is not stored.
    return _render_page(request, admin, db, new_token=token, new_token_name=record.name)


@router.post("/admin/display/tokens/{token_id}/revoke")
def revoke_token(
    token_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    revoke_display_token(db, token_id)
    return RedirectResponse("/admin/display", status_code=303)


def require_display_token(request: Request, db: sqlite3.Connection = Depends(get_db)) -> None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or verify_display_token(db, token.strip()) is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing display token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/api/display/assignments")
def display_assignments(
    days: int = 7,
    _: None = Depends(require_display_token),
    db: sqlite3.Connection = Depends(get_db),
):
    """Read-only feed for the wall display: every unfinished assignment that is overdue
    or due within the next `days` days, grouped by kid."""
    days = max(0, min(days, MAX_DAYS))
    today = date.today()
    today_str = today.isoformat()
    horizon = (today + timedelta(days=days)).isoformat()

    by_user: dict[int, list] = {}
    for a in list_all_assignments(db):
        if a.status == "done" or a.due_date > horizon:
            continue
        by_user.setdefault(a.user_id, []).append(a)

    kids = []
    for u in list_users(db):
        items = by_user.get(u.id, [])
        if not u.active or (u.is_admin and not items):
            continue
        items.sort(key=lambda a: (a.due_date, not a.priority))
        kids.append(
            {
                "name": u.display_name,
                "assignments": [
                    {
                        "subject": a.subject,
                        "title": a.title,
                        "due_date": a.due_date,
                        "status": a.status,
                        "priority": a.priority,
                        "overdue": a.due_date < today_str,
                    }
                    for a in items
                ],
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today_str,
        "days": days,
        "kids": kids,
    }
