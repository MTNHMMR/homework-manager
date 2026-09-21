import sqlite3
from datetime import date
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
    list_completed_assignments_for_user,
    sort_by_priority,
    update_assignment,
)
from app.classes import list_active_classes_for_user
from app.deps import get_db, require_user
from app.users import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _visible_assignments(assignments: list[Assignment], today: str) -> list[Assignment]:
    """Drop assignments marked done once their due date has arrived."""
    return [a for a in assignments if not (a.status == "done" and a.due_date <= today)]


@router.get("/overview", response_class=HTMLResponse)
def overview(
    request: Request,
    user: User = Depends(require_user),
    db: sqlite3.Connection = Depends(get_db),
):
    today = date.today().isoformat()
    assignments = sort_by_priority(_visible_assignments(list_assignments_for_user(db, user.id), today))
    active_classes = list_active_classes_for_user(db, user.id)
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "statuses": VALID_STATUSES,
            "active_classes": active_classes,
            "today": today,
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
