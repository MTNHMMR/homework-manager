import sqlite3
from dataclasses import dataclass
from typing import Optional

VALID_STATUSES = ("not_started", "in_progress", "done")


@dataclass
class Assignment:
    id: int
    user_id: int
    subject: str
    title: str
    due_date: str
    status: str
    priority: bool
    completed_at: Optional[str]


def _row_to_assignment(row: sqlite3.Row) -> Assignment:
    return Assignment(
        id=row["id"],
        user_id=row["user_id"],
        subject=row["subject"],
        title=row["title"],
        due_date=row["due_date"],
        status=row["status"],
        priority=bool(row["priority"]),
        completed_at=row["completed_at"],
    )


def _now(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT datetime('now')").fetchone()[0]


def create_assignment(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    title: str,
    due_date: str,
    status: str = "not_started",
    priority: bool = False,
) -> Assignment:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    completed_at = _now(conn) if status == "done" else None
    cur = conn.execute(
        "INSERT INTO assignments (user_id, subject, title, due_date, status, priority, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, subject, title, due_date, status, int(priority), completed_at),
    )
    conn.commit()
    return get_assignment_by_id(conn, cur.lastrowid)


def get_assignment_by_id(conn: sqlite3.Connection, assignment_id: int) -> Optional[Assignment]:
    row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    return _row_to_assignment(row) if row else None


def list_assignments_for_user(conn: sqlite3.Connection, user_id: int) -> list[Assignment]:
    rows = conn.execute(
        "SELECT * FROM assignments WHERE user_id = ? ORDER BY due_date", (user_id,)
    ).fetchall()
    return [_row_to_assignment(row) for row in rows]


def list_all_assignments(conn: sqlite3.Connection) -> list[Assignment]:
    rows = conn.execute("SELECT * FROM assignments ORDER BY due_date").fetchall()
    return [_row_to_assignment(row) for row in rows]


def update_assignment(
    conn: sqlite3.Connection,
    assignment_id: int,
    subject: str,
    title: str,
    due_date: str,
    status: str,
    priority: bool,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    current = get_assignment_by_id(conn, assignment_id)
    if status == "done" and current.status != "done":
        completed_at = _now(conn)
    elif status != "done":
        completed_at = None
    else:
        completed_at = current.completed_at
    conn.execute(
        "UPDATE assignments SET subject = ?, title = ?, due_date = ?, status = ?, "
        "priority = ?, completed_at = ? WHERE id = ?",
        (subject, title, due_date, status, int(priority), completed_at, assignment_id),
    )
    conn.commit()


def delete_assignment(conn: sqlite3.Connection, assignment_id: int) -> None:
    conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    conn.commit()
