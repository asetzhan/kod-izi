"""Administrator: users, roles, groups, audit journal (spec section 2, "Әкімші" row)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminUser, DbSession, client_ip
from app.api.schemas import (
    AuditEntryOut,
    GroupCreate,
    GroupOut,
    GroupUserAdd,
    RolesUpdate,
    UserBrief,
    UserCreate,
    UserOut,
)
from app.api.users import group_out
from app.core.roles import Role
from app.core.security import hash_password
from app.models import (
    AuditLog,
    Course,
    CourseGroup,
    CourseTeacher,
    Group,
    GroupMember,
    GroupTeacher,
    User,
    UserRole,
)
from app.services import audit
from app.services.audit import AuditAction
from app.services.privacy import revoke_sessions

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(max_length=100)] = None,
    role: Role | None = None,
) -> list[UserOut]:
    """Users, optionally found by a part of the name or e-mail and by role."""
    query = select(User).order_by(User.id)
    if q:
        text = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{text}%"
        query = query.where(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.full_name).like(pattern, escape="\\"),
            )
        )
    if role is not None:
        query = query.where(
            User.id.in_(select(UserRole.user_id).where(UserRole.role == role.value))
        )
    users = db.scalars(query.limit(limit).offset(offset))
    return [UserOut.from_user(u) for u in users]


class ActiveIn(BaseModel):
    active: bool


@router.put("/users/{user_id}/active")
def set_active(
    user_id: int, body: ActiveIn, request: Request, admin: AdminUser, db: DbSession
) -> UserOut:
    """A blocked user cannot sign in; their open sessions end at once."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if user.id == admin.id and not body.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_block_self")
    if user.anonymized_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="anonymized")
    user.is_active = body.active
    if not body.active:
        revoke_sessions(db, user.id)
    audit.record(
        db,
        AuditAction.USER_ACTIVATED if body.active else AuditAction.USER_DEACTIVATED,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return UserOut.from_user(user)


class PasswordIn(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: int, body: PasswordIn, request: Request, admin: AdminUser, db: DbSession
) -> UserOut:
    """A forgotten password: the administrator sets a new one; all sessions end."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if user.id == admin.id:
        # Another administrator resets it; nobody changes a password here without a witness.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_reset_own_password")
    if user.anonymized_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="anonymized")
    user.password_hash = hash_password(body.password)
    revoke_sessions(db, user.id)
    audit.record(
        db,
        AuditAction.PASSWORD_RESET,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return UserOut.from_user(user)


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


@router.get("/groups")
def list_groups(admin: AdminUser, db: DbSession) -> list[GroupOut]:
    return [group_out(db, g) for g in db.scalars(select(Group).order_by(Group.name))]


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


def _remove_from_group(
    db: DbSession,
    request: Request,
    admin: User,
    group_id: int,
    user_id: int,
    link: type[GroupMember | GroupTeacher],
    action: AuditAction,
) -> GroupOut:
    group = db.get(Group, group_id)
    row = db.get(link, (group_id, user_id))
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if row is not None:
        db.delete(row)
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


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_member(
    group_id: int, user_id: int, request: Request, admin: AdminUser, db: DbSession
) -> GroupOut:
    return _remove_from_group(
        db, request, admin, group_id, user_id, GroupMember, AuditAction.GROUP_MEMBER_REMOVED
    )


@router.delete("/groups/{group_id}/teachers/{user_id}")
def remove_teacher(
    group_id: int, user_id: int, request: Request, admin: AdminUser, db: DbSession
) -> GroupOut:
    return _remove_from_group(
        db, request, admin, group_id, user_id, GroupTeacher, AuditAction.GROUP_TEACHER_REMOVED
    )


class CourseAdminOut(BaseModel):
    id: int
    title: str
    part: str
    groups: list[UserBrief]  # id and name of each attached group
    teachers: list[UserBrief]


@router.get("/courses")
def list_courses(admin: AdminUser, db: DbSession) -> list[CourseAdminOut]:
    """Each course with its groups and teachers."""
    out = []
    for course in db.scalars(select(Course).order_by(Course.id)):
        groups = db.scalars(
            select(Group)
            .join(CourseGroup, CourseGroup.group_id == Group.id)
            .where(CourseGroup.course_id == course.id)
            .order_by(Group.name)
        )
        teachers = db.scalars(
            select(User)
            .join(CourseTeacher, CourseTeacher.user_id == User.id)
            .where(CourseTeacher.course_id == course.id)
            .order_by(User.full_name)
        )
        out.append(
            CourseAdminOut(
                id=course.id,
                title=course.title,
                part=course.part,
                groups=[UserBrief(id=g.id, full_name=g.name) for g in groups],
                teachers=[UserBrief(id=t.id, full_name=t.full_name) for t in teachers],
            )
        )
    return out


@router.delete("/courses/{course_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_group(
    course_id: int, group_id: int, request: Request, admin: AdminUser, db: DbSession
) -> None:
    row = db.get(CourseGroup, (course_id, group_id))
    if row is None:
        return
    db.delete(row)
    audit.record(
        db,
        AuditAction.COURSE_GROUP_REMOVED,
        actor_id=admin.id,
        object_type="course",
        object_id=course_id,
        ip=client_ip(request),
        details={"group_id": group_id},
    )
    db.commit()


@router.delete("/courses/{course_id}/teachers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_course_teacher(
    course_id: int, user_id: int, request: Request, admin: AdminUser, db: DbSession
) -> None:
    row = db.get(CourseTeacher, (course_id, user_id))
    if row is None:
        return
    db.delete(row)
    audit.record(
        db,
        AuditAction.COURSE_TEACHER_REMOVED,
        actor_id=admin.id,
        object_type="course",
        object_id=course_id,
        ip=client_ip(request),
        details={"user_id": user_id},
    )
    db.commit()


@router.get("/audit-log")
def audit_log(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: int | None = None,
) -> list[AuditEntryOut]:
    query = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    rows = db.scalars(query.limit(limit).offset(offset))
    return [AuditEntryOut.model_validate(r) for r in rows]
