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
