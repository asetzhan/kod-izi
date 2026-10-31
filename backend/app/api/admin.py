"""Administrator: users, roles, groups, audit journal (spec section 2, "Әкімші" row)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminUser, DbSession, client_ip
from app.api.schemas import (
    AuditEntryOut,
    GroupCreate,
    GroupOut,
    GroupUserAdd,
    RolesUpdate,
    UserCreate,
    UserOut,
)
from app.api.users import group_out
from app.core.roles import Role
from app.core.security import hash_password
from app.models import AuditLog, Group, GroupMember, GroupTeacher, User
from app.services import audit
from app.services.audit import AuditAction

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.id).limit(limit).offset(offset))
    return [UserOut.from_user(u) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, request: Request, admin: AdminUser, db: DbSession) -> UserOut:
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        password_hash=hash_password(body.password),
    )
    user.set_roles(set(body.roles))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email_taken") from None
    audit.record(
        db,
        AuditAction.USER_CREATED,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
        details={"roles": sorted(user.roles)},
    )
    db.commit()
    return UserOut.from_user(user)


@router.put("/users/{user_id}/roles")
def set_roles(
    user_id: int, body: RolesUpdate, request: Request, admin: AdminUser, db: DbSession
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    new_roles = set(body.roles)
    if user.id == admin.id and Role.ADMIN not in new_roles:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_remove_own_admin")
    before = sorted(user.roles)
    user.set_roles(new_roles)
    audit.record(
        db,
        AuditAction.ROLE_CHANGED,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
        details={"before": before, "after": sorted(new_roles)},
    )
    db.commit()
    return UserOut.from_user(user)


@router.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(body: GroupCreate, request: Request, admin: AdminUser, db: DbSession) -> GroupOut:
    group = Group(name=body.name)
    db.add(group)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="group_name_taken") from None
    audit.record(
        db,
        AuditAction.GROUP_CREATED,
        actor_id=admin.id,
        object_type="group",
        object_id=group.id,
        ip=client_ip(request),
    )
    db.commit()
    return group_out(db, group)


def _add_to_group(
    db: DbSession,
    request: Request,
    admin: User,
    group_id: int,
    user_id: int,
    required_role: Role,
    link: type[GroupMember | GroupTeacher],
    action: AuditAction,
) -> GroupOut:
    group = db.get(Group, group_id)
    user = db.get(User, user_id)
    if group is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if not user.has_role(required_role):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"user_is_not_{required_role}")
    if db.get(link, (group_id, user_id)) is None:
        db.add(link(group_id=group_id, user_id=user_id))
        audit.record(
            db,
            action,
            actor_id=admin.id,
            object_type="group",
            object_id=group_id,
            ip=client_ip(request),
            details={"user_id": user_id},
        )
        db.commit()
    return group_out(db, group)


@router.post("/groups/{group_id}/members")
def add_member(
    group_id: int, body: GroupUserAdd, request: Request, admin: AdminUser, db: DbSession
) -> GroupOut:
    return _add_to_group(
        db,
        request,
        admin,
        group_id,
        body.user_id,
        Role.STUDENT,
        GroupMember,
        AuditAction.GROUP_MEMBER_ADDED,
    )


@router.post("/groups/{group_id}/teachers")
def add_teacher(
    group_id: int, body: GroupUserAdd, request: Request, admin: AdminUser, db: DbSession
) -> GroupOut:
    return _add_to_group(
        db,
        request,
        admin,
        group_id,
        body.user_id,
        Role.TEACHER,
        GroupTeacher,
        AuditAction.GROUP_TEACHER_ADDED,
    )


@router.get("/audit-log")
def audit_log(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEntryOut]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    return [AuditEntryOut.model_validate(r) for r in rows]
