"""Courses, topics, Stepik lessons, knowledge components (ФТ-01, ФТ-08, ФТ-12)."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.content_schemas import (
    CourseCreate,
    CourseOut,
    CourseSummary,
    CourseUpdate,
    EmailIn,
    IdIn,
    TopicIn,
    TopicOut,
    topic_out,
)
from app.api.deps import AdminUser, CurrentUser, DbSession, client_ip
from app.api.schemas import GroupOut
from app.api.users import group_out
from app.core.roles import Role
from app.models import (
    Course,
    CourseGroup,
    CourseTeacher,
    ExternalLesson,
    Group,
    GroupMember,
    KnowledgeComponent,
    Topic,
    User,
)
from app.services import audit
from app.services.access import (
    can_edit_course,
    can_view_course,
    can_view_group,
    is_staff,
    studies_course,
    teaches_group,
)
from app.services.audit import AuditAction

router = APIRouter(prefix="/api", tags=["courses"])


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def _course_for_edit(db: DbSession, user: User, course_id: int) -> Course:
    if not can_edit_course(db, user, course_id):
        raise _forbidden()
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return course


@router.get("/courses")
def list_courses(user: CurrentUser, db: DbSession) -> list[CourseSummary]:
    courses = db.scalars(select(Course).order_by(Course.id)).all()
    if not is_staff(user):
        courses = [c for c in courses if studies_course(db, user.id, c.id)]
    return [CourseSummary.model_validate(c) for c in courses]


@router.post("/courses", status_code=status.HTTP_201_CREATED)
def create_course(
    body: CourseCreate, request: Request, user: CurrentUser, db: DbSession
) -> CourseOut:
    if not user.has_role(Role.TEACHER, Role.ADMIN):
        raise _forbidden()
    course = Course(title=body.title, description=body.description, part=body.part.value)
    db.add(course)
    db.flush()
    if user.has_role(Role.TEACHER):
        db.add(CourseTeacher(course_id=course.id, user_id=user.id))
    audit.record(
        db,
        AuditAction.COURSE_CREATED,
        actor_id=user.id,
        object_type="course",
        object_id=course.id,
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(course)
    return CourseOut.build(course, can_edit=True)


@router.get("/courses/{course_id}")
def get_course(course_id: int, user: CurrentUser, db: DbSession) -> CourseOut:
    if not can_view_course(db, user, course_id):
        raise _forbidden()
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return CourseOut.build(course, can_edit=can_edit_course(db, user, course_id))


@router.patch("/courses/{course_id}")
def update_course(
    course_id: int, body: CourseUpdate, request: Request, user: CurrentUser, db: DbSession
) -> CourseOut:
    course = _course_for_edit(db, user, course_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(course, field, value)
    audit.record(
        db,
        AuditAction.COURSE_UPDATED,
        actor_id=user.id,
        object_type="course",
        object_id=course.id,
        ip=client_ip(request),
    )
    db.commit()
    return CourseOut.build(course, can_edit=True)


@router.post("/courses/{course_id}/teachers")
def add_course_teacher(
    course_id: int, body: IdIn, request: Request, admin: AdminUser, db: DbSession
) -> CourseOut:
    course = _course_for_edit(db, admin, course_id)
    teacher = db.get(User, body.id)
    if teacher is None or not teacher.has_role(Role.TEACHER):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="user_is_not_teacher")
    if db.get(CourseTeacher, (course_id, teacher.id)) is None:
        db.add(CourseTeacher(course_id=course_id, user_id=teacher.id))
        audit.record(
            db,
            AuditAction.COURSE_TEACHER_ADDED,
            actor_id=admin.id,
            object_type="course",
            object_id=course_id,
            ip=client_ip(request),
            details={"user_id": teacher.id},
        )
        db.commit()
    return CourseOut.build(course, can_edit=True)


@router.post("/courses/{course_id}/groups")
def add_course_group(
    course_id: int, body: IdIn, request: Request, user: CurrentUser, db: DbSession
) -> CourseOut:
    """ФТ-01: a teacher attaches one of their own groups to their course."""
    course = _course_for_edit(db, user, course_id)
    if not user.has_role(Role.ADMIN) and not teaches_group(db, user.id, body.id):
        raise _forbidden()
    if db.get(Group, body.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if db.get(CourseGroup, (course_id, body.id)) is None:
        db.add(CourseGroup(course_id=course_id, group_id=body.id))
        audit.record(
            db,
            AuditAction.COURSE_GROUP_ADDED,
            actor_id=user.id,
            object_type="course",
            object_id=course_id,
            ip=client_ip(request),
            details={"group_id": body.id},
        )
        db.commit()
    return CourseOut.build(course, can_edit=True)


@router.get("/courses/{course_id}/groups")
def list_course_groups(course_id: int, user: CurrentUser, db: DbSession) -> list[GroupOut]:
    _course_for_edit(db, user, course_id)
    groups = db.scalars(
        select(Group)
        .join(CourseGroup, CourseGroup.group_id == Group.id)
        .where(CourseGroup.course_id == course_id)
        .order_by(Group.name)
    )
    return [group_out(db, g) for g in groups if can_view_group(db, user, g.id)]


@router.post("/groups/{group_id}/students")
def add_group_student(
    group_id: int, body: EmailIn, request: Request, user: CurrentUser, db: DbSession
) -> GroupOut:
    """ФТ-01: the group's teacher adds an existing student account by e-mail.

    Unknown e-mails, non-students and students of other groups get the same answer.
    """
    if not can_view_group(db, user, group_id):
        raise _forbidden()
    group = db.get(Group, group_id)
    student = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if student is None or not student.has_role(Role.STUDENT):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="student_not_found")
    # A teacher must not pull another teacher's student into a group to read their data:
    # only students without a group can be added; moving between groups is for admins.
    in_other_group = db.scalar(
        select(GroupMember.group_id).where(
            GroupMember.user_id == student.id, GroupMember.group_id != group_id
        )
    )
    if in_other_group is not None and not user.has_role(Role.ADMIN):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="student_not_found")
    if db.get(GroupMember, (group_id, student.id)) is None:
        db.add(GroupMember(group_id=group_id, user_id=student.id))
        audit.record(
            db,
            AuditAction.GROUP_STUDENT_ADDED,
            actor_id=user.id,
            object_type="group",
            object_id=group_id,
            ip=client_ip(request),
            details={"user_id": student.id},
        )
        db.commit()
    return group_out(db, group)


def _fill_topic(topic: Topic, body: TopicIn) -> None:
    topic.code = body.code
    topic.title = body.title
    topic.position = body.position
    topic.learning_outcomes = body.learning_outcomes
    topic.lessons = [
        ExternalLesson(
            title=lesson.title,
            url=str(lesson.url),
            stepik_lesson_id=lesson.stepik_lesson_id,
            position=i,
        )
        for i, lesson in enumerate(body.lessons, start=1)
    ]
    existing = {kc.code: kc for kc in topic.knowledge_components}
    kept = []
    for i, kc in enumerate(body.knowledge_components, start=1):
        row = existing.get(kc.code) or KnowledgeComponent(code=kc.code)
        row.name = kc.name
        row.position = i
        kept.append(row)
    topic.knowledge_components = kept


def _save_topic(db: DbSession, request: Request, user: User, topic: Topic) -> TopicOut:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="duplicate_code") from None
    audit.record(
        db,
        AuditAction.TOPIC_SAVED,
        actor_id=user.id,
        object_type="topic",
        object_id=topic.id,
        ip=client_ip(request),
    )
    db.commit()
    db.refresh(topic)
    return topic_out(topic)


@router.post("/courses/{course_id}/topics", status_code=status.HTTP_201_CREATED)
def create_topic(
    course_id: int, body: TopicIn, request: Request, user: CurrentUser, db: DbSession
) -> TopicOut:
    _course_for_edit(db, user, course_id)
    topic = Topic(course_id=course_id)
    _fill_topic(topic, body)
    db.add(topic)
    return _save_topic(db, request, user, topic)


@router.put("/topics/{topic_id}")
def update_topic(
    topic_id: int, body: TopicIn, request: Request, user: CurrentUser, db: DbSession
) -> TopicOut:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    _course_for_edit(db, user, topic.course_id)
    _fill_topic(topic, body)
    return _save_topic(db, request, user, topic)
