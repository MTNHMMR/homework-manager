import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classes import create_class, list_classes_for_user
from app.database import get_connection, init_db
from app.users import get_user_by_username

SEMESTER_EXPIRES_ON = "2026-12-31"

CLASS_LISTS = {
    "ebcain": [
        (1, "Jazz Band", "Lamar"),
        (2, "Science", "Rogers"),
        (3, "American History", "McNeil"),
        (4, "PE", "Campos"),
        (5, "ELA", "Hutson"),
        (6, "Honors Algebra", "Seyer"),
        (7, "Challenge", "Taylor"),
    ],
    "zcain": [
        (1, "Ecology", "Morton"),
        (2, "Personal Finances", "Wamble"),
        (3, "Industrial Tech", "Hobeck"),
        (4, "Advanced Foods", "Newman"),
        (5, "A+ Tutoring", None),
        (6, "College Readiness", "Taylor"),
        (7, "Marching Band", "Lamar"),
    ],
    "eacain": [
        (1, "Jazz Band", "Lamar"),
        (2, "Science", "Dugas"),
        (3, "American History", None),
        (4, "ELA", None),
        (5, "Athletic Fitness", None),
        (6, "Math", "Campos"),
        (7, "Choir", None),
    ],
}


def seed_classes() -> None:
    db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")
    conn = get_connection(db_path)
    init_db(conn)
    try:
        for username, classes in CLASS_LISTS.items():
            user = get_user_by_username(conn, username)
            if user is None:
                print(f"User '{username}' does not exist yet; skipping their classes.")
                continue
            existing_names = {c.name for c in list_classes_for_user(conn, user.id)}
            for period, name, teacher in classes:
                if name in existing_names:
                    print(f"'{username}' already has '{name}'; skipping.")
                    continue
                create_class(
                    conn,
                    user.id,
                    name,
                    teacher=teacher,
                    period=period,
                    expires_on=SEMESTER_EXPIRES_ON,
                )
                print(f"Added '{name}' (period {period}) for '{username}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed_classes()
