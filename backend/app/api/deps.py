from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.roles import Role
from app.core.security import decode_access_token
from app.db.context import set_actor
from app.db.session import get_db
from app.models import User
from app.services.two_factor import has_second_factor, needs_second_factor

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_redis() -> Redis:
    return _redis_client()


RedisClient = Annotated[Redis, Depends(get_redis)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="not_authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Reachable before the second factor is set up or consent is given.
OPEN_PATHS = {
    "/api/me",
    "/api/auth/2fa/setup",
    "/api/auth/2fa/enable",
    "/api/consent",
    "/api/consent/withdraw",
}


def get_current_user(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    except jwt.InvalidTokenError:
        raise _unauthorized() from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    set_actor(db, user)  # row-level security sees this user from now on
    if request.url.path not in OPEN_PATHS:
        if (
            settings.require_2fa_for_staff
            and needs_second_factor(user)
            and not has_second_factor(user)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="2fa_required")
        if (
            settings.require_consent
            and user.has_role(Role.STUDENT)
            and not is_staff_user(user)
            and (user.consent_version != settings.consent_version or user.consent_withdrawn_at)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="consent_required")
    return user


def is_staff_user(user: User) -> bool:
    return user.has_role(Role.TEACHER, Role.COACH, Role.ADMIN)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Role check (spec section 2). Roles come from the database, not the token,
    so a role change applies to tokens already issued."""

    def dependency(user: CurrentUser) -> User:
        if not user.has_role(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return dependency


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
