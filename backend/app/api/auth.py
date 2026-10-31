"""Login, refresh, logout (spec 14.1, "Кіру" row)."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AppSettings, DbSession, RedisClient, client_ip
from app.api.schemas import LoginRequest, TokenResponse, UserOut
from app.core.config import Settings
from app.core.security import create_access_token
from app.models import User
from app.services import audit
from app.services.audit import AuditAction
from app.services.auth import (
    LocalPasswordBackend,
    RefreshError,
    TokenReuseError,
    issue_refresh_token,
    revoke_by_raw,
    rotate_refresh_token,
)
from app.services.privacy import email_hash
from app.services.rate_limit import LoginRateLimiter
from app.services.two_factor import accept as accept_totp
from app.services.two_factor import has_second_factor, needs_second_factor

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"
# Refresh and logout use a cookie, so they also require a custom header: a cross-site
# form cannot send it, and a cross-site fetch with it needs a CORS preflight we never allow.
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "kod-izi"

_backend = LocalPasswordBackend()


def _token_response(user: User, refresh_raw: str, settings: Settings) -> JSONResponse:
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    body = TokenResponse(
        access_token=create_access_token(user.id, settings.jwt_secret, ttl),
        expires_in=int(ttl.total_seconds()),
        user=UserOut.from_user(user),
    )
    response = JSONResponse(body.model_dump(mode="json"))
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_raw,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return response


def _clear_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _require_csrf_header(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="csrf_header_missing")


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: DbSession,
    redis: RedisClient,
    settings: AppSettings,
) -> JSONResponse:
    email = body.email.strip().lower()
    ip = client_ip(request)
    limiter = LoginRateLimiter(redis, settings.login_max_attempts, settings.login_window_seconds)

    if not limiter.register_attempt(email, ip):
        audit.record(
            db,
            AuditAction.LOGIN_FAILED,
            ip=ip,
            details={
                "email_hash": email_hash(email, settings.jwt_secret),
                "reason": "rate_limited",
            },
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts")

    user = _backend.authenticate(db, email, body.password)
    if user is None:
        audit.record(
            db,
            AuditAction.LOGIN_FAILED,
            ip=ip,
            details={
                "email_hash": email_hash(email, settings.jwt_secret),
                "reason": "invalid_credentials",
            },
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if needs_second_factor(user) and has_second_factor(user):
        reason = None
        if not body.otp:
            reason = "otp_required"
        elif not accept_totp(user, str(user.totp_secret), body.otp):
            reason = "otp_invalid"
        if reason is not None:
            audit.record(
                db, AuditAction.LOGIN_FAILED, actor_id=user.id, ip=ip, details={"reason": reason}
            )
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=reason)

    limiter.reset(email, ip)
    refresh_raw = issue_refresh_token(
        db, user.id, settings, user_agent=request.headers.get("user-agent"), ip=ip
    )
    audit.record(db, AuditAction.LOGIN_SUCCESS, actor_id=user.id, ip=ip)
    db.commit()
    return _token_response(user, refresh_raw, settings)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, db: DbSession, settings: AppSettings) -> JSONResponse:
    _require_csrf_header(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    failure = JSONResponse({"detail": "invalid_refresh_token"}, status.HTTP_401_UNAUTHORIZED)
    _clear_cookie(failure, settings)
    if not raw:
        return failure
    ip = client_ip(request)
    try:
        user, new_raw = rotate_refresh_token(
            db, raw, settings, user_agent=request.headers.get("user-agent"), ip=ip
        )
    except TokenReuseError as exc:
        audit.record(db, AuditAction.TOKEN_REUSE_DETECTED, actor_id=exc.user_id, ip=ip)
        db.commit()
        return failure
    except RefreshError:
        db.rollback()
        return failure
    db.commit()
    return _token_response(user, new_raw, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: DbSession, settings: AppSettings) -> Response:
    _require_csrf_header(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        user_id = revoke_by_raw(db, raw)
        if user_id is not None:
            audit.record(db, AuditAction.LOGOUT, actor_id=user_id, ip=client_ip(request))
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookie(response, settings)
    return response
