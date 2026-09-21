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


def test_init_db_migrates_existing_assignments_table_missing_priority_and_completed_columns(tmp_path):
    db_path = tmp_path / "old_assignments.db"
    conn = get_connection(db_path)
    # Create users table first to satisfy foreign key constraint
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
        ("testuser", "hash", "Test User"),
    )
    conn.execute(
        """
        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO assignments (user_id, subject, title, due_date) VALUES (?, ?, ?, ?)",
        (1, "Math", "Worksheet", "2026-09-25"),
    )
    conn.commit()

    init_db(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
    assert "priority" in columns
    assert "completed_at" in columns
    row = conn.execute(
        "SELECT priority, completed_at FROM assignments WHERE subject = 'Math'"
    ).fetchone()
    assert row["priority"] == 0
    assert row["completed_at"] is None
    conn.close()


def test_init_db_assignments_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "new_assignments.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)  # must not raise "duplicate column name"
    conn.close()


def test_fresh_install_assignments_table_already_has_new_columns(tmp_path):
    db_path = tmp_path / "fresh_assignments.db"
    conn = get_connection(db_path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()}
    assert "priority" in columns
    assert "completed_at" in columns
    conn.close()
