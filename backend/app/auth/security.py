"""Password hashing and signed access tokens (JWT)."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(hours=24)

_password_hash = PasswordHash.recommended()  # Argon2


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + TOKEN_LIFETIME}
    return jwt.encode(payload, get_settings().jwt_secret.get_secret_value(), algorithm=ALGORITHM)


def read_access_token(token: str) -> int | None:
    """Return the user id inside the token, or None if the token is invalid or expired."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None