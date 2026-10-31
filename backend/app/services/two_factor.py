"""Second factor for teachers and administrators (spec 14.1, "Кіру" row): TOTP (RFC 6238)."""

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


def verify(secret: str, code: str) -> bool:
    """One 30-second step of clock drift is accepted either way."""
    code = code.strip().replace(" ", "")
    return code.isdigit() and len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)
