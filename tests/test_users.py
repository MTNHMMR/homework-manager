import sqlite3

import pytest

from app.theming import VALID_ACCENTS, VALID_THEMES
from app.users import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    list_users,
    set_user_active,
    set_user_password,
    set_user_theme,
)
from app.security import verify_password


def test_create_user_hashes_password(db):
    user = create_user(db, "kid1", "hunter2", "Kid One")
    assert user.username == "kid1"
    assert user.display_name == "Kid One"
    assert user.is_admin is False
    assert user.active is True
    assert verify_password("hunter2", user.password_hash)


def test_create_user_defaults_to_non_admin_and_can_be_admin(db):
    kid = create_user(db, "kid1", "pw", "Kid One")
    admin = create_user(db, "parent1", "pw", "Parent One", is_admin=True)
    assert kid.is_admin is False
    assert admin.is_admin is True


def test_create_user_rejects_duplicate_username(db):
    create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(sqlite3.IntegrityError):
        create_user(db, "kid1", "pw2", "Kid One Again")


def test_get_user_by_id_roundtrip(db):
    created = create_user(db, "kid1", "pw", "Kid One")
    fetched = get_user_by_id(db, created.id)
    assert fetched == created


def test_get_user_by_id_missing_returns_none(db):
    assert get_user_by_id(db, 999) is None


def test_get_user_by_username_missing_returns_none(db):
    assert get_user_by_username(db, "nobody") is None


def test_list_users_returns_all(db):
    create_user(db, "kid1", "pw", "Kid One")
    create_user(db, "kid2", "pw", "Kid Two")
    usernames = {u.username for u in list_users(db)}
    assert usernames == {"kid1", "kid2"}


def test_set_user_active_deactivates(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    set_user_active(db, user.id, False)
    assert get_user_by_id(db, user.id).active is False


def test_set_user_password_updates_hash(db):
    user = create_user(db, "kid1", "oldpw", "Kid One")
    set_user_password(db, user.id, "newpw")
    updated = get_user_by_id(db, user.id)
    assert verify_password("newpw", updated.password_hash)
    assert not verify_password("oldpw", updated.password_hash)


def test_new_user_gets_default_theme_and_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    assert user.theme == "light"
    assert user.accent_color == "blue"


def test_set_user_theme_updates_theme_and_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    set_user_theme(db, user.id, "dark", "teal")
    updated = get_user_by_id(db, user.id)
    assert updated.theme == "dark"
    assert updated.accent_color == "teal"


def test_set_user_theme_rejects_invalid_theme(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(ValueError):
        set_user_theme(db, user.id, "neon", "blue")


def test_set_user_theme_rejects_invalid_accent(db):
    user = create_user(db, "kid1", "pw", "Kid One")
    with pytest.raises(ValueError):
        set_user_theme(db, user.id, "light", "chartreuse")


def test_valid_themes_and_accents_constants():
    assert VALID_THEMES == ("light", "dark", "fun", "minimal")
    assert VALID_ACCENTS == ("red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")
