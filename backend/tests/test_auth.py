import importlib
import os

import pytest
from fastapi import HTTPException

# Ensure auth module can be imported during test collection.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
from app import auth as auth_module


def _reload_auth(secret: str):
    os.environ["JWT_SECRET_KEY"] = secret
    return importlib.reload(auth_module)


def test_hash_and_verify_password_round_trip() -> None:
    auth = _reload_auth("test-secret")
    hashed = auth.hash_password("super-secret")
    assert auth.verify_password("super-secret", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    auth = _reload_auth("test-secret")
    hashed = auth.hash_password("correct")
    assert auth.verify_password("wrong", hashed) is False


def test_create_and_decode_token_success() -> None:
    auth = _reload_auth("test-secret")
    token = auth.create_token("user-1", "user@example.com")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"
    assert "exp" in payload


def test_decode_token_invalid_raises_http_401() -> None:
    auth = _reload_auth("test-secret")
    with pytest.raises(HTTPException, match="Invalid or expired token") as exc:
        auth.decode_token("not-a-valid-token")
    assert exc.value.status_code == 401


def test_get_current_user_requires_bearer_header() -> None:
    auth = _reload_auth("test-secret")
    with pytest.raises(HTTPException, match="Missing or invalid Authorization header") as exc:
        auth.get_current_user("Token abc")
    assert exc.value.status_code == 401


def test_get_current_user_parses_valid_bearer_token() -> None:
    auth = _reload_auth("test-secret")
    token = auth.create_token("user-2", "u2@example.com")
    current = auth.get_current_user(f"Bearer {token}")
    assert current["sub"] == "user-2"


def test_get_optional_user_returns_none_for_missing_or_bad_header() -> None:
    auth = _reload_auth("test-secret")
    assert auth.get_optional_user(None) is None
    assert auth.get_optional_user("Token abc") is None


def test_get_optional_user_returns_none_for_bad_token() -> None:
    auth = _reload_auth("test-secret")
    assert auth.get_optional_user("Bearer invalid") is None


def test_get_optional_user_returns_payload_for_valid_token() -> None:
    auth = _reload_auth("test-secret")
    token = auth.create_token("user-3", "u3@example.com")
    payload = auth.get_optional_user(f"Bearer {token}")
    assert payload is not None
    assert payload["email"] == "u3@example.com"
