"""Object-level access checks (spec 14.1, "Рұқсаттар" row).

All "who may see what" rules live here, so row-level security can later mirror them.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models import GroupMember, GroupTeacher, User


def teaches_group(db: Session, teacher_id: int, group_id: int) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    GroupTeacher.user_id == teacher_id, GroupTeacher.group_id == group_id
                )
            )
        )
    )


def can_view_user(db: Session, viewer: User, target_id: int) -> bool:
    if viewer.has_role(Role.ADMIN) or viewer.id == target_id:
        return True
    if not viewer.has_role(Role.TEACHER):
        return False
    shared_group = (
        select(GroupMember.group_id)
        .join(GroupTeacher, GroupTeacher.group_id == GroupMember.group_id)
        .where(GroupMember.user_id == target_id, GroupTeacher.user_id == viewer.id)
    )
    return bool(db.scalar(select(exists(shared_group))))


def can_view_group(db: Session, viewer: User, group_id: int) -> bool:
    if viewer.has_role(Role.ADMIN):
        return True
    return viewer.has_role(Role.TEACHER) and teaches_group(db, viewer.id, group_id)
