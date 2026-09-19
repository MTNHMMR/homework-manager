import pytest

from app.database import get_connection, init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = get_connection(path)
    init_db(conn)
    conn.close()
    return path


@pytest.fixture
def db(db_path):
    conn = get_connection(db_path)
    yield conn
    conn.close()


@pytest.fixture
def make_user(db):
    from app.users import create_user

    def _make(username, password="password123", display_name=None, is_admin=False):
        return create_user(
            db, username, password, display_name or username.title(), is_admin=is_admin
        )

    return _make
