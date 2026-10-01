import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps import get_db, require_admin
from app.users import (
    User,
    count_other_active_admins,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    set_user_active,
    set_user_password,
    update_user,
)
from app.templating import templates

router = APIRouter()


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
    if target.is_admin and count_other_active_admins(db, user_id) == 0:
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


def _render_edit(request: Request, admin: User, target: User, form: dict, error: Optional[str] = None):
    return templates.TemplateResponse(
        "admin_user_edit.html",
        {"request": request, "user": admin, "target": target, "form": form, "error": error},
        status_code=400 if error else 200,
    )


@router.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user_form(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    target = get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    form = {
        "username": target.username,
        "display_name": target.display_name,
        "is_admin": target.is_admin,
    }
    return _render_edit(request, admin, target, form)


@router.post("/admin/users/{user_id}/edit")
def edit_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    is_admin: Optional[str] = Form(None),
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    target = get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    username = username.strip()
    display_name = display_name.strip()
    make_admin = is_admin is not None
    form = {"username": username, "display_name": display_name, "is_admin": make_admin}

    if not username or not display_name:
        return _render_edit(request, admin, target, form, "Name and username are required.")
    existing = get_user_by_username(db, username)
    if existing is not None and existing.id != user_id:
        return _render_edit(request, admin, target, form, "That username is already taken.")
    if (
        target.is_admin
        and target.active
        and not make_admin
        and count_other_active_admins(db, user_id) == 0
    ):
        return _render_edit(
            request, admin, target, form, "You can't remove admin from the last active admin."
        )

    update_user(db, user_id, username, display_name, make_admin)
    # An admin who just removed their own admin flag can no longer see this page.
    if user_id == admin.id and not make_admin:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/delete")
def remove_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
):
    target = get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    if target.is_admin and target.active and count_other_active_admins(db, user_id) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last active admin")
    delete_user(db, user_id)
    return RedirectResponse("/admin/users", status_code=303)
