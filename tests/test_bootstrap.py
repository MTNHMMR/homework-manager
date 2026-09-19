from app.users import get_user_by_username
from scripts.bootstrap_admin import bootstrap_admin


def test_bootstrap_creates_admin_when_none_exists(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_USERNAME", "parent1")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Parent One")

    bootstrap_admin()

    admin = get_user_by_username(db, "parent1")
    assert admin is not None
    assert admin.is_admin is True
    assert admin.display_name == "Parent One"


def test_bootstrap_is_idempotent(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_USERNAME", "parent1")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
    monkeypatch.setenv("ADMIN_DISPLAY_NAME", "Parent One")

    bootstrap_admin()
    bootstrap_admin()  # must not raise or create a duplicate

    from app.users import list_users

    matching = [u for u in list_users(db) if u.username == "parent1"]
    assert len(matching) == 1


def test_bootstrap_skips_when_env_vars_missing(db_path, db, monkeypatch, capsys):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    bootstrap_admin()

    from app.users import list_users

    assert list_users(db) == []
