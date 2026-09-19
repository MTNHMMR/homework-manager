import os

from app.database import get_connection, init_db
from app.users import create_user, get_user_by_username


def bootstrap_admin() -> None:
    db_path = os.environ.get("HOMEWORK_DB_PATH", "homework.db")
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    display_name = os.environ.get("ADMIN_DISPLAY_NAME") or username or "Admin"

    if not username or not password:
        print("ADMIN_USERNAME and ADMIN_PASSWORD not set; skipping admin bootstrap.")
        return

    conn = get_connection(db_path)
    init_db(conn)
    try:
        if get_user_by_username(conn, username) is not None:
            print(f"Admin user '{username}' already exists; skipping.")
            return
        create_user(conn, username, password, display_name, is_admin=True)
        print(f"Created admin user '{username}'.")
    finally:
        conn.close()


if __name__ == "__main__":
    bootstrap_admin()
