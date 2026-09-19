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
    target = get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_admin:
        active_admin_count = sum(1 for u in list_users(db) if u.is_admin and u.active)
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
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
