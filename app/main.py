# app/main.py
import os

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_connection, init_db


class CSRFMiddleware(BaseHTTPMiddleware):
    """Block browser cross-site state-changing requests.

    Combined with SameSite=Strict session cookies, this protects form POSTs
    without requiring every template and route to manage CSRF tokens.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
                return PlainTextResponse("Cross-site request blocked", status_code=403)

            expected_host = request.headers.get("host", "").lower()
            for header_name in ("origin", "referer"):
                value = request.headers.get(header_name)
                if value:
                    actual_host = urlsplit(value).netloc.lower()
                    if actual_host and actual_host != expected_host:
                        return PlainTextResponse("Cross-site request blocked", status_code=403)
                    break

        return await call_next(request)
from app.routers import admin, admin_classes, admin_users, auth, overview, settings


def create_app() -> FastAPI:
    app = FastAPI(title="Homework Manager")

    app.state.db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")

    secret_key = os.environ.get("SESSION_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SESSION_SECRET_KEY environment variable must be set")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        same_site="strict",
        https_only=os.environ.get("SESSION_HTTPS_ONLY", "0") == "1",
    )
    app.add_middleware(CSRFMiddleware)

    conn = get_connection(app.state.db_path)
    init_db(conn)
    conn.close()

    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    app.include_router(auth.router)
    app.include_router(overview.router)
    app.include_router(admin.router)
    app.include_router(admin_classes.router)
    app.include_router(admin_users.router)
    app.include_router(settings.router)

    return app
