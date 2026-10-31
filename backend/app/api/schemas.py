from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.roles import Role
from app.models import User


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[Role]
    is_active: bool
    two_factor_enabled: bool = False
    consent_version: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            roles=sorted(user.roles),
            is_active=user.is_active,
            two_factor_enabled=user.totp_enabled_at is not None,
            consent_version=None if user.consent_withdrawn_at else user.consent_version,
        )


class UserBrief(BaseModel):
    id: int
    full_name: str


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)
    otp: str | None = Field(default=None, max_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)
    roles: list[Role] = Field(min_length=1)


class RolesUpdate(BaseModel):
    roles: list[Role] = Field(min_length=1)


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GroupUserAdd(BaseModel):
    user_id: int


class GroupOut(BaseModel):
    id: int
    name: str
    students: list[UserBrief]
    teachers: list[UserBrief]


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_id: int | None
    action: str
    object_type: str | None
    object_id: str | None
    ip: str | None
    details: dict[str, Any]
