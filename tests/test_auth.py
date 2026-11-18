import pytest
import time
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.core.rate_limiter import is_rate_limited, record_failed_attempt, clear_rate_limit


def test_argon2id_hashing():
    password = "StrongPassword@2026"
    pwd_hash = hash_password(password)

    assert pwd_hash.startswith("$argon2id$")
    assert verify_password(password, pwd_hash) is True
    assert verify_password("WrongPassword", pwd_hash) is False


def test_jwt_token():
    payload = {"sub": "admin", "role": "superadmin"}
    token = create_access_token(payload)

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "admin"
    assert decoded["role"] == "superadmin"


def test_rate_limiter():
    key = "127.0.0.1:test_rate_user"
    clear_rate_limit(key)

    limited, _ = is_rate_limited(key)
    assert limited is False

    # Simulate 5 failed attempts
    for _ in range(5):
        record_failed_attempt(key)

    limited, retry_after = is_rate_limited(key)
    assert limited is True
    assert retry_after > 0

    # Clear rate limit upon successful login
    clear_rate_limit(key)
    limited, _ = is_rate_limited(key)
    assert limited is False
