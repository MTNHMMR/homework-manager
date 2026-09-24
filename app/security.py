import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


MIN_PASSWORD_LENGTH = 8
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 300

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

_login_failures = defaultdict(deque)
_login_lock = Lock()


def password_validation_error(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def _login_key(username: str) -> str:
    return username.strip().casefold()


def login_retry_after(username: str) -> int:
    """Return seconds until another attempt is allowed, or 0 if allowed."""
    key = _login_key(username)
    now = monotonic()
    cutoff = now - LOGIN_WINDOW_SECONDS
    with _login_lock:
        failures = _login_failures[key]
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if len(failures) < LOGIN_MAX_FAILURES:
            return 0
        return max(1, int(LOGIN_WINDOW_SECONDS - (now - failures[0])))


def record_login_failure(username: str) -> None:
    key = _login_key(username)
    now = monotonic()
    cutoff = now - LOGIN_WINDOW_SECONDS
    with _login_lock:
        failures = _login_failures[key]
        while failures and failures[0] <= cutoff:
            failures.popleft()
        failures.append(now)


def clear_login_failures(username: str) -> None:
    with _login_lock:
        _login_failures.pop(_login_key(username), None)
