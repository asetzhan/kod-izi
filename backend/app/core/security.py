"""Password hashing and tokens (spec 14.1: Argon2id, short-lived JWT, revocable refresh token)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ALGORITHM = "HS256"

_hasher = PasswordHasher()  # argon2id with library defaults

# Verified against when the user does not exist, so both paths take similar time.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, secret: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> int:
    """Return the user id; raise jwt.InvalidTokenError on any problem."""
    payload = jwt.decode(
        token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "type"]}
    )
    if payload["type"] != "access":
        raise jwt.InvalidTokenError("not an access token")
    return int(payload["sub"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
