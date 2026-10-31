"""Current user and user lookup with object-level checks (spec 14.1, "Рұқсаттар" row)."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import GroupOut, UserBrief, UserOut
from app.models import Group, GroupMember, GroupTeacher, User
from app.services.access import can_view_group, can_view_user

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)


@router.get("/users/{user_id}")
def get_user(user_id: int, viewer: CurrentUser, db: DbSession) -> UserOut:
    # Permission first: a forbidden id and a missing id look the same to non-admins.
    if not can_view_user(db, viewer, user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return UserOut.from_user(user)


def _group_users(
    db: DbSession, group_id: int, link: type[GroupMember | GroupTeacher]
) -> list[UserBrief]:
    rows = db.scalars(
        select(User)
        .join(link, link.user_id == User.id)
        .where(link.group_id == group_id)
        .order_by(User.full_name)
    )
    return [UserBrief(id=u.id, full_name=u.full_name) for u in rows]


def group_out(db: DbSession, group: Group) -> GroupOut:
    return GroupOut(
        id=group.id,
        name=group.name,
        students=_group_users(db, group.id, GroupMember),
        teachers=_group_users(db, group.id, GroupTeacher),
    )


@router.get("/groups/{group_id}")
def get_group(group_id: int, viewer: CurrentUser, db: DbSession) -> GroupOut:
    if not can_view_group(db, viewer, group_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return group_out(db, group)
