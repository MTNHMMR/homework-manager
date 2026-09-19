import sqlite3
from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request

from app.database import get_connection
from app.users import User, get_user_by_id


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    request: Request, db: sqlite3.Connection = Depends(get_db)
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = get_user_by_id(db, user_id)
    if user is None or not user.active:
        return None
    return user


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user
