import sqlite3
from dataclasses import dataclass
from typing import Optional

from app.security import hash_password
from app.theming import VALID_ACCENTS, VALID_THEMES


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    display_name: str
    is_admin: bool
    active: bool
    theme: str
    accent_color: str


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
        is_admin=bool(row["is_admin"]),
        active=bool(row["active"]),
        theme=row["theme"],
        accent_color=row["accent_color"],
    )


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    display_name: str,
    is_admin: bool = False,
) -> User:
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) "
        "VALUES (?, ?, ?, ?)",
        (username, hash_password(password), display_name, int(is_admin)),
    )
    conn.commit()
    return get_user_by_id(conn, cur.lastrowid)


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[User]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[User]:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _row_to_user(row) if row else None


def list_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute("SELECT * FROM users ORDER BY display_name").fetchall()
    return [_row_to_user(row) for row in rows]


def set_user_active(conn: sqlite3.Connection, user_id: int, active: bool) -> None:
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
    conn.commit()


def set_user_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()


def set_user_theme(
    conn: sqlite3.Connection, user_id: int, theme: str, accent_color: str
) -> None:
    if theme not in VALID_THEMES:
        raise ValueError(f"invalid theme: {theme}")
    if accent_color not in VALID_ACCENTS:
        raise ValueError(f"invalid accent_color: {accent_color}")
    conn.execute(
        "UPDATE users SET theme = ?, accent_color = ? WHERE id = ?",
        (theme, accent_color, user_id),
    )
    conn.commit()
