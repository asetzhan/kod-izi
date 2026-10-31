"""Second factor for teachers and administrators (spec 14.1, "Кіру" row): TOTP (RFC 6238)."""

import hmac
import time
from datetime import UTC, datetime

import pyotp

from app.core.roles import Role
from app.models import User

ISSUER = "Kod Izi"
STAFF_2FA_ROLES = (Role.TEACHER, Role.ADMIN)


def needs_second_factor(user: User) -> bool:
    return user.has_role(*STAFF_2FA_ROLES)


def has_second_factor(user: User) -> bool:
    return user.totp_secret is not None and user.totp_enabled_at is not None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)


def _matching_step(secret: str, code: str, now: float | None = None) -> int | None:
    """The time step the code belongs to; one 30-second step of clock drift either way."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(_datetime(now))
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def _datetime(now: float | None) -> datetime:
    return datetime.fromtimestamp(time.time() if now is None else now, UTC)


def accept(user: User, secret: str, code: str, now: float | None = None) -> bool:
    """Check the code and remember its step: a code works once (no replay within its window).

    The caller commits; the step is stored on the user."""
    step = _matching_step(secret, code, now)
    if step is None or (user.totp_last_step is not None and step <= user.totp_last_step):
        return False
    user.totp_last_step = step
    return True
