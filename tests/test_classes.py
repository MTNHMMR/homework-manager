from datetime import date

from app.classes import (
    create_class,
    delete_class,
    get_class_by_id,
    list_active_classes_for_user,
    list_classes_for_user,
    update_class,
)


def test_create_class_with_all_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Science", teacher="Rogers", period=2, expires_on="2026-12-31")
    assert c.name == "Science"
    assert c.teacher == "Rogers"
    assert c.period == 2
    assert c.expires_on == "2026-12-31"


def test_create_class_with_minimal_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "A+ Tutoring")
    assert c.teacher is None
    assert c.period is None
    assert c.expires_on is None


def test_get_class_by_id_missing_returns_none(db):
    assert get_class_by_id(db, 999) is None


def test_list_classes_for_user_orders_by_period_then_name(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Third", period=3)
    create_class(db, kid.id, "First", period=1)
    create_class(db, kid.id, "NoPeriod")
    names = [c.name for c in list_classes_for_user(db, kid.id)]
    assert names == ["First", "Third", "NoPeriod"]


def test_list_classes_for_user_only_that_users_classes(db, make_user):
    kid1 = make_user("kid1")
    kid2 = make_user("kid2")
    create_class(db, kid1.id, "Math")
    create_class(db, kid2.id, "Science")
    names = [c.name for c in list_classes_for_user(db, kid1.id)]
    assert names == ["Math"]


def test_list_active_classes_excludes_expired(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Expired", expires_on="2026-01-01")
    create_class(db, kid.id, "Active", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 9, 20))
    assert [c.name for c in active] == ["Active"]


def test_list_active_classes_includes_never_expiring(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Forever", expires_on=None)
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 9, 20))
    assert [c.name for c in active] == ["Forever"]


def test_list_active_classes_boundary_inclusive_on_expiry_date(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "LastDay", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2026, 12, 31))
    assert [c.name for c in active] == ["LastDay"]


def test_list_active_classes_excludes_day_after_expiry(db, make_user):
    kid = make_user("kid1")
    create_class(db, kid.id, "Expired", expires_on="2026-12-31")
    active = list_active_classes_for_user(db, kid.id, today=date(2027, 1, 1))
    assert active == []


def test_update_class_changes_fields(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Math", period=1)
    update_class(db, c.id, "Advanced Math", "Smith", 2, "2026-12-31")
    updated = get_class_by_id(db, c.id)
    assert updated.name == "Advanced Math"
    assert updated.teacher == "Smith"
    assert updated.period == 2
    assert updated.expires_on == "2026-12-31"


def test_delete_class_removes_it(db, make_user):
    kid = make_user("kid1")
    c = create_class(db, kid.id, "Math")
    delete_class(db, c.id)
    assert get_class_by_id(db, c.id) is None
