"""Audit journal writer (spec 14.1, "Аудит" row)."""

from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


class AuditAction(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REUSE_DETECTED = "token_reuse_detected"  # noqa: S105  # nosec B105
    USER_CREATED = "user_created"
    ROLE_CHANGED = "role_changed"
    GROUP_CREATED = "group_created"
    GROUP_MEMBER_ADDED = "group_member_added"
    GROUP_TEACHER_ADDED = "group_teacher_added"
    GROUP_STUDENT_ADDED = "group_student_added"
    COURSE_CREATED = "course_created"
    COURSE_UPDATED = "course_updated"
    COURSE_TEACHER_ADDED = "course_teacher_added"
    COURSE_GROUP_ADDED = "course_group_added"
    TOPIC_SAVED = "topic_saved"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_IMPORTED = "task_imported"
    TASK_LEVEL_SUGGESTED = "task_level_suggested"
    TASK_LEVEL_CONFIRMED = "task_level_confirmed"
    TASK_APPROVED = "task_approved"
    ASSESSMENT_SAVED = "assessment_saved"
    SETTING_CHANGED = "setting_changed"
    RUBRIC_UPDATED = "rubric_updated"
    MATERIAL_UPLOADED = "material_uploaded"
    MATERIAL_BOUND = "material_bound"
    AI_GRADE_REQUESTED = "ai_grade_requested"
    COMPONENT_EDITED = "component_edited"
    COMPONENT_GENERATED = "component_generated"
    GRADE_CONFIRMED = "grade_confirmed"
    OBSERVATION_ADDED = "observation_added"
    TWO_FACTOR_ENABLED = "two_factor_enabled"
    TWO_FACTOR_RESET = "two_factor_reset"
    CONSENT_GIVEN = "consent_given"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    USER_ANONYMIZED = "user_anonymized"
    DATA_EXPORTED = "data_exported"
    FILE_LINK_ISSUED = "file_link_issued"
    CONTEST_SAVED = "contest_saved"
    VIRTUAL_CONTEST_STARTED = "virtual_contest_started"
    OLYMPIAD_SETTINGS_CHANGED = "olympiad_settings_changed"
    TASK_ASSIGNED = "task_assigned"
    TASK_UNASSIGNED = "task_unassigned"
    TASK_GENERATED = "task_generated"
    RUBRIC_EXAMPLE_ADDED = "rubric_example_added"
    RUBRIC_EXAMPLE_REMOVED = "rubric_example_removed"


def record(
    db: Session,
    action: AuditAction,
    *,
    actor_id: int | None = None,
    object_type: str | None = None,
    object_id: int | str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an entry to the session; it is written with the caller's commit."""
    db.add(
        AuditLog(
            action=action.value,
            actor_id=actor_id,
            object_type=object_type,
            object_id=None if object_id is None else str(object_id),
            ip=ip,
            details=details or {},
        )
    )
