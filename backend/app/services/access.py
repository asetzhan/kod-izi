"""Object-level access checks (spec 14.1, "Рұқсаттар" row).

All "who may see what" rules live here, so row-level security can later mirror them.
Staff (teacher, coach, admin) read the shared course catalogue and task bank; only
teachers of a course and admins change it. Students see only courses of their groups.
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models import CourseGroup, CourseTeacher, GroupMember, GroupTeacher, User

STAFF = (Role.TEACHER, Role.COACH, Role.ADMIN)


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


def is_staff(user: User) -> bool:
    return user.has_role(*STAFF)


def teaches_course(db: Session, user_id: int, course_id: int) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    CourseTeacher.user_id == user_id, CourseTeacher.course_id == course_id
                )
            )
        )
    )


def can_edit_course(db: Session, user: User, course_id: int) -> bool:
    if user.has_role(Role.ADMIN):
        return True
    return user.has_role(Role.TEACHER) and teaches_course(db, user.id, course_id)


def studies_course(db: Session, student_id: int, course_id: int) -> bool:
    enrolled = (
        select(CourseGroup.course_id)
        .join(GroupMember, GroupMember.group_id == CourseGroup.group_id)
        .where(GroupMember.user_id == student_id, CourseGroup.course_id == course_id)
    )
    return bool(db.scalar(select(exists(enrolled))))


def can_view_course(db: Session, user: User, course_id: int) -> bool:
    if is_staff(user):
        return True
    return user.has_role(Role.STUDENT) and studies_course(db, user.id, course_id)
