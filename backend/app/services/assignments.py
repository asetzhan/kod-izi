"""ФТ-05: tasks the teacher gives one student; worked on outside assessments."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import TaskStatus
from app.models import Task, TaskAssignment
from app.services.contests import in_unfinished_contest


def assignment_for(db: Session, user_id: int, task_id: int) -> TaskAssignment | None:
    return db.scalar(
        select(TaskAssignment).where(
            TaskAssignment.user_id == user_id, TaskAssignment.task_id == task_id
        )
    )


def can_work_on_assignment(db: Session, user_id: int, task: Task) -> bool:
    """An approved task given to this student; never a problem of an unfinished contest."""
    return (
        task.status == TaskStatus.APPROVED.value
        and assignment_for(db, user_id, task.id) is not None
        and not in_unfinished_contest(db, task.id, datetime.now(UTC))
    )
