import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Class:
    id: int
    user_id: int
    name: str
    teacher: Optional[str]
    period: Optional[int]
    expires_on: Optional[str]


def _row_to_class(row: sqlite3.Row) -> Class:
    return Class(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        teacher=row["teacher"],
        period=row["period"],
        expires_on=row["expires_on"],
    )


def create_class(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    teacher: Optional[str] = None,
    period: Optional[int] = None,
    expires_on: Optional[str] = None,
) -> Class:
    cur = conn.execute(
        "INSERT INTO classes (user_id, name, teacher, period, expires_on) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, name, teacher, period, expires_on),
    )
    conn.commit()
    return get_class_by_id(conn, cur.lastrowid)


def get_class_by_id(conn: sqlite3.Connection, class_id: int) -> Optional[Class]:
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    return _row_to_class(row) if row else None


def list_classes_for_user(conn: sqlite3.Connection, user_id: int) -> list[Class]:
    rows = conn.execute(
        "SELECT * FROM classes WHERE user_id = ? ORDER BY period IS NULL, period, name",
        (user_id,),
    ).fetchall()
    return [_row_to_class(row) for row in rows]


def list_active_classes_for_user(
    conn: sqlite3.Connection, user_id: int, today: Optional[date] = None
) -> list[Class]:
    today_str = (today or date.today()).isoformat()
    rows = conn.execute(
        "SELECT * FROM classes WHERE user_id = ? "
        "AND (expires_on IS NULL OR expires_on >= ?) "
        "ORDER BY period IS NULL, period, name",
        (user_id, today_str),
    ).fetchall()
    return [_row_to_class(row) for row in rows]


def update_class(
    conn: sqlite3.Connection,
    class_id: int,
    name: str,
    teacher: Optional[str],
    period: Optional[int],
    expires_on: Optional[str],
) -> None:
    conn.execute(
        "UPDATE classes SET name = ?, teacher = ?, period = ?, expires_on = ? WHERE id = ?",
        (name, teacher, period, expires_on, class_id),
    )
    conn.commit()


def delete_class(conn: sqlite3.Connection, class_id: int) -> None:
    conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    conn.commit()
