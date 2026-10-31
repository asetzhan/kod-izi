"""Stage 5 API: second factor, consent, anonymization, pilot data export (ФТ-49 core).

Spec 13, 14.1, 14.3, 16.
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AdminUser, AppSettings, CurrentUser, DbSession, client_ip
from app.api.schemas import UserOut
from app.models import AiGrade, Assessment, Submission, TeacherGrade, User
from app.services import audit
from app.services.access import can_edit_course
from app.services.audit import AuditAction
from app.services.privacy import anonymize
from app.services.research import agreement, pseudonym
from app.services.rubrics import CRITERIA_CODES
from app.services.two_factor import new_secret, provisioning_uri, verify

router = APIRouter(prefix="/api", tags=["privacy"])


# Second factor (spec 14.1) -------------------------------------------------------------


class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str


@router.post("/auth/2fa/setup")
def setup_two_factor(user: CurrentUser, db: DbSession) -> TwoFactorSetup:
    """A new secret for the authenticator app; it works only after `enable`."""
    if user.totp_enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="2fa_already_enabled")
    secret = new_secret()
    user.totp_pending_secret = secret
    db.commit()
    return TwoFactorSetup(secret=secret, otpauth_uri=provisioning_uri(user, secret))


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


@router.post("/auth/2fa/enable")
def enable_two_factor(body: CodeIn, request: Request, user: CurrentUser, db: DbSession) -> UserOut:
    if user.totp_pending_secret is None or not verify(user.totp_pending_secret, body.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="otp_invalid")
    user.totp_secret = user.totp_pending_secret
    user.totp_pending_secret = None
    user.totp_enabled_at = datetime.now(UTC)
    audit.record(
        db,
        AuditAction.TWO_FACTOR_ENABLED,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return UserOut.from_user(user)


@router.post("/admin/users/{user_id}/2fa/reset")
def reset_two_factor(user_id: int, request: Request, admin: AdminUser, db: DbSession) -> UserOut:
    """For a lost phone: the user sets up the second factor again at the next login."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    user.totp_secret = user.totp_pending_secret = None
    user.totp_enabled_at = None
    audit.record(
        db,
        AuditAction.TWO_FACTOR_RESET,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return UserOut.from_user(user)


# Consent (spec 13, 14.3) -----------------------------------------------------------------


class ConsentOut(BaseModel):
    version: str
    accepted_version: str | None
    accepted_at: datetime | None
    withdrawn_at: datetime | None


def _consent(user: User, settings: AppSettings) -> ConsentOut:
    return ConsentOut(
        version=settings.consent_version,
        accepted_version=user.consent_version,
        accepted_at=user.consent_at,
        withdrawn_at=user.consent_withdrawn_at,
    )


@router.get("/consent")
def read_consent(user: CurrentUser, settings: AppSettings) -> ConsentOut:
    return _consent(user, settings)


class ConsentIn(BaseModel):
    version: str = Field(max_length=16)


@router.post("/consent")
def give_consent(
    body: ConsentIn, request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> ConsentOut:
    """The student accepts processing of their data and AI-assisted assessment (14.3)."""
    if body.version != settings.consent_version:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="consent_outdated")
    user.consent_version = body.version
    user.consent_at = datetime.now(UTC)
    user.consent_withdrawn_at = None
    audit.record(
        db,
        AuditAction.CONSENT_GIVEN,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
        details={"version": body.version},
    )
    db.commit()
    return _consent(user, settings)


@router.post("/consent/withdraw")
def withdraw_consent(
    request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> ConsentOut:
    """14.3: consent can be withdrawn; the data is then anonymized by the retention job."""
    user.consent_withdrawn_at = datetime.now(UTC)
    audit.record(
        db,
        AuditAction.CONSENT_WITHDRAWN,
        actor_id=user.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return _consent(user, settings)


@router.post("/admin/users/{user_id}/anonymize")
def anonymize_user(user_id: int, request: Request, admin: AdminUser, db: DbSession) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cannot_anonymize_self")
    anonymize(db, user)
    audit.record(
        db,
        AuditAction.USER_ANONYMIZED,
        actor_id=admin.id,
        object_type="user",
        object_id=user.id,
        ip=client_ip(request),
    )
    db.commit()
    return UserOut.from_user(user)


# Pilot data (ФТ-49 core, spec 16) -------------------------------------------------------


def _rows(db: DbSession, assessment: Assessment, secret: str) -> list[dict[str, Any]]:
    """One row per submission that has both an AI grade and a teacher's grade."""
    rows = []
    submissions = db.scalars(
        select(Submission).where(Submission.assessment_id == assessment.id).order_by(Submission.id)
    )
    for submission in submissions:
        teacher = db.scalar(
            select(TeacherGrade)
            .where(TeacherGrade.submission_id == submission.id)
            .order_by(TeacherGrade.id.desc())
        )
        if teacher is None:
            continue
        ai = db.get(AiGrade, teacher.ai_grade_id) if teacher.ai_grade_id else None
        ai_levels = {c["code"]: c["level"] for c in ai.criteria} if ai else {}
        t_levels = {c["code"]: c["level"] for c in teacher.criteria}
        row: dict[str, Any] = {
            "student": pseudonym(submission.user_id, secret),
            "task_id": submission.task_id,
            "submission_id": submission.id,
            "verdict": submission.verdict,
            "ai_status": ai.status if ai else "",
            "ai_model": ai.model if ai else "",
            "ai_prompt_version": ai.prompt_version if ai else "",
            "ai_F": ai.component_f if ai else "",
            "ai_E": ai.component_e if ai else "",
            "ai_A": ai.component_a if ai else "",
            "ai_S": ai.score if ai else "",
            "teacher_F": teacher.component_f,
            "teacher_E": teacher.component_e,
            "teacher_A": teacher.component_a,
            "teacher_S": teacher.score,
        }
        for code in CRITERIA_CODES:
            row[f"ai_{code}"] = ai_levels.get(code, "")
            row[f"teacher_{code}"] = t_levels.get(code, "")
        rows.append(row)
    return rows


def _assessment_for_teacher(db: DbSession, user: User, assessment_id: int) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or not can_edit_course(db, user, assessment.course_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
    return assessment


@router.get("/assessments/{assessment_id}/export.csv")
def export_csv(
    assessment_id: int, request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> Response:
    """AI and teacher grades side by side, students under pseudonyms (ФТ-49)."""
    assessment = _assessment_for_teacher(db, user, assessment_id)
    rows = _rows(db, assessment, settings.jwt_secret)
    buffer = io.StringIO()
    columns = list(rows[0]) if rows else ["student", "task_id", "submission_id"]
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    audit.record(
        db,
        AuditAction.DATA_EXPORTED,
        actor_id=user.id,
        object_type="assessment",
        object_id=assessment_id,
        ip=client_ip(request),
        details={"rows": len(rows)},
    )
    db.commit()
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="assessment-{assessment_id}.csv"'},
    )


@router.get("/assessments/{assessment_id}/agreement")
def assessment_agreement(
    assessment_id: int, user: CurrentUser, db: DbSession, settings: AppSettings
) -> dict[str, Any]:
    """Pearson, Spearman, MAE and MD between AI and teacher for S, F, E and A (spec 16)."""
    assessment = _assessment_for_teacher(db, user, assessment_id)
    rows = [r for r in _rows(db, assessment, settings.jwt_secret) if r["ai_S"] != ""]
    out: dict[str, Any] = {"baseline": {"mae": 7.34, "pearson": 0.647, "model": "Claude"}}
    for key in ("S", "F", "E", "A"):
        out[key] = agreement(
            [float(r[f"ai_{key}"]) for r in rows], [float(r[f"teacher_{key}"]) for r in rows]
        )
    return out
