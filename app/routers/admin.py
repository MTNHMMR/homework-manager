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
    list_all_completed_assignments,
    sort_by_priority,
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
