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
