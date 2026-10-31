"""Authentication and refresh-token rotation (spec 14.1, "Кіру" row; Q-03: local login only)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User


class AuthBackend(Protocol):
    """Extension point: an SSO backend (Moodle, Platonus) can be added beside the local one."""

    def authenticate(self, db: Session, email: str, password: str) -> User | None: ...


class LocalPasswordBackend:
    def authenticate(self, db: Session, email: str, password: str) -> User | None:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            verify_password(DUMMY_PASSWORD_HASH, password)
            return None
        if not verify_password(user.password_hash, password) or not user.is_active:
            return None
        return user


class RefreshError(Exception):
    pass


class TokenReuseError(RefreshError):
    def __init__(self, user_id: int) -> None:
        super().__init__("refresh token reused")
        self.user_id = user_id


def issue_refresh_token(
    db: Session,
    user_id: int,
    settings: Settings,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    raw = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:255] or None,
            ip=ip,
        )
    )
    return raw


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def rotate_refresh_token(
    db: Session,
    raw: str,
    settings: Settings,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[User, str]:
    """Revoke the presented token and issue the next one in the same family.

    A token that was already revoked means it leaked: the whole family is revoked.
    """
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
    )
    if row is None:
        raise RefreshError("unknown token")
    if row.revoked_at is not None:
        revoke_family(db, row.family_id)
        raise TokenReuseError(row.user_id)
    if row.expires_at <= datetime.now(UTC):
        raise RefreshError("expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RefreshError("inactive user")
    row.revoked_at = datetime.now(UTC)
    new_raw = issue_refresh_token(
        db, user.id, settings, family_id=row.family_id, user_agent=user_agent, ip=ip
    )
    return user, new_raw


def revoke_by_raw(db: Session, raw: str) -> int | None:
    """Revoke the family of the presented token; return its user id if it was known."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    if row is None:
        return None
    revoke_family(db, row.family_id)
    return row.user_id
