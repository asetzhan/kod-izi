from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import Role
from app.db.base import Base

_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in Role)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Spec 14.1: second factor (TOTP) for teachers and administrators.
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_pending_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last accepted TOTP time step: a code is accepted only once.
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    # Spec 13, 14.3: consent to processing personal data (version of the text accepted).
    consent_version: Mapped[str | None] = mapped_column(String(16))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role_links: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def roles(self) -> set[Role]:
        return {Role(link.role) for link in self.role_links}

    def has_role(self, *roles: Role) -> bool:
        return bool(self.roles.intersection(roles))

    def set_roles(self, roles: set[Role]) -> None:
        current = {link.role: link for link in self.role_links}
        for role in set(current) - {r.value for r in roles}:
            self.role_links.remove(current[role])
        for role in roles:
            if role.value not in current:
                self.role_links.append(UserRole(role=role.value))


class UserRole(Base):
    """A person may hold several roles, e.g. teacher and coach (spec section 2)."""

    __tablename__ = "user_roles"
    __table_args__ = (CheckConstraint(f"role IN ({_ROLE_VALUES})", name="role_valid"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), primary_key=True)

    user: Mapped[User] = relationship(back_populates="role_links")
