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
from app.users import User, get_user_by_id, list_users

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


def _require_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Class name is required")
    return cleaned


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
    target = get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_admin:
        raise HTTPException(
            status_code=400, detail="Classes can only be assigned to kid accounts"
        )
    name = _require_name(name)
    try:
        create_class(
            db,
            user_id,
            name,
            teacher=_clean_optional(teacher),
            period=_parse_period(period),
            expires_on=_clean_optional(expires_on),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    name = _require_name(name)
    try:
        update_class(
            db,
            class_id,
            name,
            _clean_optional(teacher),
            _parse_period(period),
            _clean_optional(expires_on),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
