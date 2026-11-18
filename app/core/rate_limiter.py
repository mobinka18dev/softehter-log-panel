import time
from collections import defaultdict
from threading import Lock
from app.config import settings

# Thread-safe in-memory rate limiter for login attempts
_lock = Lock()
_attempts: dict[str, list[float]] = defaultdict(list)
_lockouts: dict[str, float] = {}


def is_rate_limited(identifier: str) -> tuple[bool, int]:
    """
    Check if an identifier (e.g. IP or username) is rate limited.
    Returns (is_limited, seconds_remaining).
    """
    now = time.time()
    with _lock:
        # Check if explicitly locked out
        if identifier in _lockouts:
            unlock_time = _lockouts[identifier]
            if now < unlock_time:
                return True, int(unlock_time - now)
            else:
                del _lockouts[identifier]
                _attempts[identifier] = []

        # Clean old attempts outside the window
        window_seconds = settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60
        valid_attempts = [t for t in _attempts[identifier] if now - t < window_seconds]
        _attempts[identifier] = valid_attempts

        if len(valid_attempts) >= settings.MAX_LOGIN_ATTEMPTS:
            # Lock out for the remainder of the window
            unlock_time = valid_attempts[0] + window_seconds
            _lockouts[identifier] = unlock_time
            return True, max(1, int(unlock_time - now))

        return False, 0


def record_failed_attempt(identifier: str) -> None:
    """Record a failed login attempt."""
    now = time.time()
    with _lock:
        _attempts[identifier].append(now)
        window_seconds = settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60
        valid_attempts = [t for t in _attempts[identifier] if now - t < window_seconds]
        _attempts[identifier] = valid_attempts

        if len(valid_attempts) >= settings.MAX_LOGIN_ATTEMPTS:
            _lockouts[identifier] = now + window_seconds


def clear_rate_limit(identifier: str) -> None:
    """Clear failed attempts on successful login."""
    with _lock:
        if identifier in _attempts:
            del _attempts[identifier]
        if identifier in _lockouts:
            del _lockouts[identifier]
