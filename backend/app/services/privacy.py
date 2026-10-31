"""Personal data (spec 13, 14.1, 14.3): consent, anonymization, retention, signed links."""

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.core.security import hash_password
from app.models import RefreshToken, Submission, TraceEvent, User
from app.services.auth import revoke_family


def anonymize(db: Session, user: User) -> None:
    """Remove what identifies the person; the trace and grades stay, linked only to the id.

    Trace and audit rows are append-only (CLAUDE.md), so the person is removed from the
    user record instead of deleting their history.
    """
    user.full_name = f"Жойылған пайдаланушы #{user.id}"
    user.email = f"deleted-{user.id}@invalid.local"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.is_active = False
    user.totp_secret = None
    user.totp_pending_secret = None
    user.totp_enabled_at = None
    user.anonymized_at = datetime.now(UTC)
    families = db.scalars(
        select(RefreshToken.family_id).where(RefreshToken.user_id == user.id).distinct()
    )
    for family in families:
        revoke_family(db, family)


def last_activity(db: Session, user_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(TraceEvent.server_ts)).where(TraceEvent.user_id == user_id)
    ) or db.scalar(select(func.max(Submission.created_at)).where(Submission.user_id == user_id))


def apply_retention(db: Session, retention_days: int, now: datetime | None = None) -> list[int]:
    """Anonymize students who withdrew consent, or were inactive longer than the retention
    period (spec 14.3: «Деректерді сақтау мерзімі мен жою тәртібі»)."""
    now = now or datetime.now(UTC)
    limit = now - timedelta(days=retention_days)
    done = []
    for user in db.scalars(select(User).where(User.anonymized_at.is_(None))):
        if not user.has_role(Role.STUDENT) or user.has_role(Role.TEACHER, Role.COACH, Role.ADMIN):
            continue
        seen = last_activity(db, user.id) or user.created_at
        if user.consent_withdrawn_at is not None or seen < limit:
            anonymize(db, user)
            done.append(user.id)
    return done


def _signature(secret: str, material_id: int, version_id: int, expires: int) -> str:
    message = f"material:{material_id}:{version_id}:{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def sign_link(secret: str, material_id: int, version_id: int, ttl_seconds: int) -> tuple[int, str]:
    expires = int(time.time()) + ttl_seconds
    return expires, _signature(secret, material_id, version_id, expires)


def link_is_valid(
    secret: str, material_id: int, version_id: int, expires: int, signature: str
) -> bool:
    if expires < int(time.time()):
        return False
    expected = _signature(secret, material_id, version_id, expires)
    return hmac.compare_digest(expected, signature)
