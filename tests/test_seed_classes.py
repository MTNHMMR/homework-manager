from app.classes import list_classes_for_user
from app.users import create_user, get_user_by_username
from scripts.seed_classes import seed_classes


def test_seed_classes_creates_classes_for_existing_user(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    names = {c.name for c in classes}
    assert "Ecology" in names
    assert "Marching Band" in names
    assert len(classes) == 7


def test_seed_classes_sets_expiration_on_every_class(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    assert all(c.expires_on == "2026-12-31" for c in classes)


def test_seed_classes_skips_missing_users(db_path, db, monkeypatch, capsys):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    seed_classes()
    captured = capsys.readouterr()
    assert "does not exist yet" in captured.out


def test_seed_classes_is_idempotent(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "zcain", "pw", "Zander")

    seed_classes()
    seed_classes()

    zander = get_user_by_username(db, "zcain")
    classes = list_classes_for_user(db, zander.id)
    assert len(classes) == 7


def test_seed_classes_seeds_elizabeths_full_list(db_path, db, monkeypatch):
    monkeypatch.setenv("HOMEWORK_DB_PATH", str(db_path))
    create_user(db, "eacain", "pw", "Elizabeth")

    seed_classes()

    elizabeth = get_user_by_username(db, "eacain")
    classes = list_classes_for_user(db, elizabeth.id)
    names = {c.name for c in classes}
    assert names == {
        "Jazz Band",
        "Science",
        "American History",
        "ELA",
        "Athletic Fitness",
        "Math",
        "Choir",
    }
    assert len(classes) == 7
