import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class DisplayToken:
    id: int
    name: str
    last_used_at: Optional[str]
    created_at: str


def _hash(token: str) -> str:
    # Tokens are 256-bit random values, so a fast hash is enough; bcrypt is for
    # low-entropy passwords.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_token(row: sqlite3.Row) -> DisplayToken:
    return DisplayToken(
        id=row["id"],
        name=row["name"],
        last_used_at=row["last_used_at"],
        created_at=row["created_at"],
    )


def create_display_token(conn: sqlite3.Connection, name: str) -> tuple[DisplayToken, str]:
    """Returns the stored token record plus the plaintext token, which is never stored."""
    token = secrets.token_urlsafe(32)
    cur = conn.execute(
        "INSERT INTO display_tokens (name, token_hash) VALUES (?, ?)", (name, _hash(token))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM display_tokens WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_token(row), token


def list_display_tokens(conn: sqlite3.Connection) -> list[DisplayToken]:
    rows = conn.execute("SELECT * FROM display_tokens ORDER BY created_at, id").fetchall()
    return [_row_to_token(row) for row in rows]


def revoke_display_token(conn: sqlite3.Connection, token_id: int) -> None:
    conn.execute("DELETE FROM display_tokens WHERE id = ?", (token_id,))
    conn.commit()


def verify_display_token(conn: sqlite3.Connection, token: str) -> Optional[DisplayToken]:
    row = conn.execute(
        "SELECT * FROM display_tokens WHERE token_hash = ?", (_hash(token),)
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE display_tokens SET last_used_at = datetime('now', 'localtime') WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    return _row_to_token(row)
