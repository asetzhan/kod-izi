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
from app.db.session import get_db
from app.models import User

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


def get_current_user(
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
    return user


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
