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
