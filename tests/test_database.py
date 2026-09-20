import sqlite3
from app.database import get_connection, init_db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)

    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"users", "assignments"} <= tables
    conn.close()


def test_get_connection_uses_row_factory(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    assert conn.row_factory is sqlite3.Row
    conn.close()


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise
    conn.close()


def test_init_db_creates_classes_table(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "classes" in tables
    conn.close()


def test_init_db_migrates_existing_users_table_missing_theme_columns(tmp_path):
    db_path = tmp_path / "old.db"
    conn = get_connection(db_path)
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
        ("kid1", "hash", "Kid One"),
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "theme" in columns
    assert "accent_color" in columns
    row = conn.execute(
        "SELECT theme, accent_color FROM users WHERE username = 'kid1'"
    ).fetchone()
    assert row["theme"] == "light"
    assert row["accent_color"] == "blue"
    conn.close()


def test_init_db_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "new.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise "duplicate column name"
    conn.close()


def test_fresh_install_users_table_already_has_theme_columns(tmp_path):
    db_path = tmp_path / "fresh.db"
    conn = get_connection(db_path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "theme" in columns
    assert "accent_color" in columns
    conn.close()
