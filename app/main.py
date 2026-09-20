# app/main.py
import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_connection, init_db
from app.routers import admin, admin_classes, admin_users, auth, overview, settings


def create_app() -> FastAPI:
    app = FastAPI(title="Homework Manager")

    app.state.db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")

    secret_key = os.environ.get("SESSION_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SESSION_SECRET_KEY environment variable must be set")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

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
